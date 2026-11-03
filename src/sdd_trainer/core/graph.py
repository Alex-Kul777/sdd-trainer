"""LangGraph graph of the trainer (criteria 2, 4 and 5).

Topology — AIA_06 routing-agent template: assess -> route -> teach / quiz,
with a clarification loop:

- ``assess`` — ask the calibration question (HITL via ``interrupt`` /
  ``Command(resume=...)``, AIA_03/07) and produce a structured
  ``Assessment`` via ``llm_call`` (ADR-005). The passive part of the
  assessment (``analyze_student_repo``, task 3.1 / T6, issue #7): when a
  student repo is configured, the scan runs after the answer and its
  evidence is weighed against the self-report — the tool call lands in
  the session log (course criterion 3); a scan failure degrades to a
  self-report-only assessment;
- ``route`` — routing node with >= 3 paths: knows_it / partial / new_topic
  plus ``clarification`` when the assessment is inconclusive (confidence
  below the threshold) — course criterion 5. A confident assessment is
  routed by GigaChat through a structured ``RouteDecision`` call; a
  low-confidence one is routed to ``clarification`` deterministically, and
  after ``max_clarification_rounds`` the graph falls back to the assessed
  level so the loop stays bounded;
- ``clarify`` — ask a follow-up question (``interrupt``) and re-assess with
  all answers so far, then return to ``route``;
- ``teach`` — unfolds the lesson skeleton into a full lesson under the
  assessed level (T4, issue #5, ADR-009): loads the skeleton (fixed
  sections, validated), asks through a structured ``DocsDecision`` whether
  the skeleton alone is enough, pulls fresh documentation via
  ``search_sdd_docs`` (Tavily, ADR-006) when it is not — the tool call and
  its results land in the session log (spec scenario) — and unfolds
  skeleton + docs into the lesson text (plain completion: prose, not a
  structured decision);
- ``quiz`` — the knowledge check (T5, issue #6, ADR-009): questions from
  the authored ``data/quizzes/<domain>.json``, one ``interrupt`` per
  question, answers scored by the deterministic token F1 of ``core.quiz``
  against the reference answers (no LLM judge — reproducible), progress
  (score, streak) recorded into ``training-state.json`` (task 4.2).

Every node appends human-readable entries to the ``log`` channel, so the
selected route is visible in the session log (spec: routing scenario). The
graph is transport-agnostic: console (phase 1), FastAPI (phase 2), MCP
(phase 3) all drive the same compiled graph. Implemented by the
``add-console-trainer`` change (phase 1, issue #4).
"""
from __future__ import annotations

import operator
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.core.prompts import (
    CALIBRATION_QUESTION,
    build_assessment_messages,
    build_clarifying_question,
    build_docs_decision_messages,
    build_reassessment_messages,
    build_route_messages,
    build_teach_messages,
    default_docs_query,
)
from sdd_trainer.core.quiz import score_quiz
from sdd_trainer.core.tools import analyze_student_repo, search_sdd_docs
from sdd_trainer.lessons import load_lesson_skeleton, load_quiz
from sdd_trainer.models import Assessment, DocsDecision, RepoAnalysis, RouteDecision

#: Confidence below this routes to ``clarification`` (spec: inconclusive
#: assessment). Assessments at or above it are routed by the LLM call.
CLARIFICATION_THRESHOLD = 0.5

#: Hard bound on clarification rounds per session: after this many
#: low-confidence rounds the graph follows the assessed level instead of
#: asking again, so the loop can never run forever.
MAX_CLARIFICATION_ROUNDS = 2


class TrainerState(TypedDict):
    """State channels of the trainer graph (persisted by the checkpointer).

    ``log`` and ``clarification_answers`` accumulate across nodes (and across
    sessions on the same thread) via the ``operator.add`` reducer; the other
    channels hold the latest value. Pydantic models are stored as plain
    dicts so the state serializes cleanly into SQLite checkpoints.
    """

    domain: str
    calibration_answer: str
    assessment: dict
    repo_analysis: dict
    route: dict
    clarification_rounds: int
    clarification_answers: Annotated[list[str], operator.add]
    log: Annotated[list[str], operator.add]
    teach_output: str
    quiz_output: str
    quiz_result: dict


def build_graph(
    llm: LLMManager,
    *,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    clarification_threshold: float = CLARIFICATION_THRESHOLD,
    max_clarification_rounds: int = MAX_CLARIFICATION_ROUNDS,
    docs_search: Optional[Callable[[str], list[dict]]] = None,
    state_store: Optional[TrainingStateStore] = None,
    repo_path: Optional[str] = None,
    repo_analyzer: Optional[Callable[[str], RepoAnalysis]] = None,
):
    """Assemble and compile the trainer StateGraph (criterion 2).

    Args:
        llm: the LLM client used by the assess / route / clarify / teach
            nodes (the single test seam — unit tests inject a fake client,
            design.md).
        checkpointer: persistence for criterion 4 (ADR-008). The console
            wires a ``SqliteSaver`` via ``MemoryManager``; unit tests use
            ``InMemorySaver`` or a temporary ``SqliteSaver``. A session with
            ``interrupt`` requires a checkpointer.
        clarification_threshold: assessment confidence below this routes to
            the clarification path.
        max_clarification_rounds: after this many clarification rounds the
            graph follows the assessed level even at low confidence.
        docs_search: the fresh-docs tool the teach node pulls documentation
            through on demand (task 3.3) — the real ``search_sdd_docs``
            (Tavily, ADR-006) by default; unit tests inject a fake callable
            (same seam discipline: external collaborators are faked at the
            graph boundary, never internal ones mocked).
        state_store: the training-state persistence the quiz node records
            progress through (task 4.2, ADR-008) — a
            :class:`~sdd_trainer.core.memory.TrainingStateStore` over
            ``data/training-state.json`` by default; unit tests inject one
            over a tmp path so they never touch the repo's runtime data.
        repo_path: path to the student's repository for the passive
            assessment (task 3.1, issue #7) — CLI ``--repo-path`` in the
            console. ``None`` (default) skips the passive scan: the
            assessment falls back to the self-report alone.
        repo_analyzer: the repo-scan tool the assess node pulls evidence
            through — the real ``analyze_student_repo`` by default; unit
            tests inject a fake callable (the same seam discipline as
            ``docs_search``: external collaborators are faked at the graph
            boundary, never internal ones mocked).

    Returns:
        The compiled graph: invoke it with ``{"domain": ...}`` and a
        ``{"configurable": {"thread_id": ...}}`` config, then answer the
        interrupts with ``Command(resume=...)``.
    """
    if docs_search is None:
        docs_search = search_sdd_docs
    if state_store is None:
        state_store = TrainingStateStore()
    if repo_analyzer is None:
        repo_analyzer = analyze_student_repo

    def assess_node(state: TrainerState) -> dict:
        """Calibration question, then assess with passive repo evidence (3.1).

        The question goes through ``interrupt`` (HITL, AIA_03/07): the first
        execution pauses the graph — the checkpoint stores the pending
        question — and ``Command(resume=answer)`` re-enters the node with
        the student's answer. No LLM call happens before the answer.

        Task 3.1 (issue #7): when ``repo_path`` is configured, the passive
        scan runs *after* the interrupt (the node re-executes on resume, so
        the scan would run twice if it sat before the interrupt) and its
        evidence is weighed against the self-report in the assessment
        prompt. The tool call lands in the session log (criterion 3); a
        scan failure degrades honestly to a self-report-only assessment —
        only the exception type is logged (secret hygiene convention).
        """
        answer = interrupt(CALIBRATION_QUESTION)
        log: list[str] = []
        analysis: RepoAnalysis | None = None
        if repo_path:
            try:
                analysis = repo_analyzer(repo_path)
            except Exception as exc:
                log.append(
                    "Инструмент analyze_student_repo(\"{}\") не смог "
                    "проанализировать репозиторий ({}) — оценка по "
                    "самоотчёту".format(repo_path, type(exc).__name__)
                )
            else:
                log.append(
                    "Инструмент analyze_student_repo(\"{}\"): {}".format(
                        repo_path, analysis.summary
                    )
                )
        assessment = llm.llm_call(
            build_assessment_messages(answer, repo_analysis=analysis), Assessment
        )
        return {
            "calibration_answer": answer,
            "assessment": assessment.model_dump(),
            "repo_analysis": analysis.model_dump() if analysis else {},
            "clarification_rounds": 0,
            # per-session outputs: clear values left over from a previous
            # session on the same thread (channels persist across runs)
            "teach_output": "",
            "quiz_output": "",
            "quiz_result": {},
            "log": log
            + [
                "Оценка: {} (уверенность {:.2f}) — {}".format(
                    assessment.level, assessment.confidence, assessment.justification
                )
            ],
        }

    def route_node(state: TrainerState) -> dict:
        """Select the lesson path: knows_it / partial / new_topic (+ clarification).

        Course criterion 5. Policy (task 3.2):

        - confidence below the threshold and rounds left → ``clarification``
          (deterministic — the spec ties this path to inconclusive
          assessments, so it must not depend on the LLM's mood);
        - confidence below the threshold but no rounds left → follow the
          assessed level (bounded loop);
        - otherwise → GigaChat decides through a structured
          ``RouteDecision`` call (ADR-005; the AIA_06 routing-agent pattern).
        """
        assessment = Assessment.model_validate(state["assessment"])
        rounds = state.get("clarification_rounds", 0)
        if assessment.confidence < clarification_threshold:
            if rounds < max_clarification_rounds:
                decision = RouteDecision(
                    path="clarification",
                    reason=(
                        "уверенность оценки {:.2f} ниже порога {:.2f} — "
                        "задаю уточняющий вопрос".format(
                            assessment.confidence, clarification_threshold
                        )
                    ),
                )
            else:
                decision = RouteDecision(
                    path=assessment.level,
                    reason=(
                        "уверенность по-прежнему низкая, но предел уточнений "
                        "({}) достигнут — веду по уровню {}".format(
                            max_clarification_rounds, assessment.level
                        )
                    ),
                )
        else:
            decision = llm.llm_call(build_route_messages(assessment), RouteDecision)
        return {
            "route": decision.model_dump(),
            "log": ["Маршрут: {} — {}".format(decision.path, decision.reason)],
        }

    def clarify_node(state: TrainerState) -> dict:
        """Ask a follow-up question, re-assess with all answers, return to route.

        Like ``assess``, the question goes through ``interrupt``; the
        re-assessment sees the calibration answer, every clarification
        answer, and the previous assessment.
        """
        assessment = Assessment.model_validate(state["assessment"])
        question = build_clarifying_question(assessment)
        answer = interrupt(question)
        answers_so_far = [*state.get("clarification_answers", []), answer]
        new_assessment = llm.llm_call(
            build_reassessment_messages(
                state["calibration_answer"], answers_so_far, assessment
            ),
            Assessment,
        )
        rounds = state.get("clarification_rounds", 0) + 1
        return {
            "assessment": new_assessment.model_dump(),
            "clarification_answers": [answer],
            "clarification_rounds": rounds,
            "log": [
                "Уточнение (раунд {}): {}".format(rounds, question),
                "Переоценка: {} (уверенность {:.2f}) — {}".format(
                    new_assessment.level,
                    new_assessment.confidence,
                    new_assessment.justification,
                ),
            ],
        }

    def teach_node(state: TrainerState) -> dict:
        """Unfold the lesson skeleton into a lesson under the assessed level.

        Task 3.3 (T4, issue #5, ADR-009). The level reaches the node from the
        assessment — ``state["assessment"]["level"]`` (set by assess/clarify
        in T3) — and selects the unfolding strategy (new_topic / partial /
        knows_it directives in ``core.prompts``); the justification carries
        the gaps to close. Flow:

        1. load the domain skeleton (fixed ADR-009 sections, validated);
        2. ask through the structured seam whether the skeleton suffices
           (``DocsDecision``, ADR-005); when it does not, pull fresh
           documentation via ``search_sdd_docs`` (Tavily, ADR-006) — the
           tool call and its results land in the session log (spec
           scenario). A search failure degrades to a skeleton-only lesson:
           the exception *type* is logged, never the payload;
        3. unfold skeleton + (optional) fresh docs into the lesson text —
           a plain completion, because the lesson is prose, not a decision.
        """
        domain = state["domain"]
        level = state["assessment"]["level"]
        justification = state["assessment"]["justification"]
        skeleton = load_lesson_skeleton(domain)

        decision = llm.llm_call(
            build_docs_decision_messages(skeleton, level, justification),
            DocsDecision,
        )
        log = [
            "Материалы: {} — {}".format(
                "нужен свежий поиск"
                if decision.needs_docs
                else "скелета достаточно",
                decision.reason,
            )
        ]

        search_results: list[dict] = []
        if decision.needs_docs:
            # Live models occasionally ask for docs but omit the query
            # (seen in the live demo 02.11) — the intent is the model's, the
            # mechanics are deterministic: fall back to the domain default.
            query = decision.query.strip() or default_docs_query(domain)
            try:
                search_results = docs_search(query)
            except Exception as exc:
                # Resilience boundary: a search outage must not kill the
                # lesson — the skeleton is the primary material. Only the
                # exception type is logged (secret hygiene convention).
                log.append(
                    "Инструмент search_sdd_docs(\"{}\") не смог выполнить "
                    "поиск ({}) — урок строится по скелету".format(
                        query, type(exc).__name__
                    )
                )
            else:
                if search_results:
                    found = "; ".join(
                        "{} — {}".format(result["title"], result["url"])
                        for result in search_results
                    )
                    log.append(
                        "Инструмент search_sdd_docs(\"{}\"): {} "
                        "результат(ов) — {}".format(
                            query, len(search_results), found
                        )
                    )
                else:
                    log.append(
                        "Инструмент search_sdd_docs(\"{}\"): ничего не "
                        "найдено".format(query)
                    )

        lesson = llm.complete(
            build_teach_messages(skeleton, level, justification, search_results)
        )
        log.append(
            "Урок готов: скелет {} развёрнут под уровень {}".format(domain, level)
        )
        return {"teach_output": lesson, "log": log}

    def quiz_node(state: TrainerState) -> dict:
        """Ask the JSON-quiz questions and score F1 against the references.

        Task 3.4 (T5, issue #6, ADR-009). The questions come from the
        authored ``data/quizzes/<domain>.json`` — one ``interrupt`` per
        question (HITL, AIA_03/07; LangGraph matches resume values to
        interrupts by order, so every answer lands in its checkpoint and a
        mid-quiz restart re-asks only the pending question). Scoring is the
        deterministic token F1 of ``core.quiz`` — reproducible, no LLM
        judge (ADR-009: reference answers + weights). The weighted score
        and verdict land in ``quiz_result`` / ``quiz_output``, and the
        domain progress (score, streak — task 4.2) is recorded through the
        training-state store so it survives a restart (ADR-008).
        """
        domain = state["domain"]
        quiz = load_quiz(domain)
        log = [
            "Проверка знаний: {} вопрос(ов) по домену {}".format(
                len(quiz.questions), domain
            )
        ]

        answers: list[str] = []
        for question in quiz.questions:
            answers.append(interrupt(question.question))

        outcome = score_quiz(quiz, answers)
        for question, f1 in zip(quiz.questions, outcome.question_f1s):
            log.append(
                "Вопрос {}: F1 = {:.2f}".format(
                    question.id or question.question[:30], f1
                )
            )
        log.append(
            "Квиз {}: {:.2f} (порог {:.2f})".format(
                "зачтён" if outcome.result.passed else "не зачтён",
                outcome.result.score,
                quiz.pass_threshold,
            )
        )

        entry = state_store.record_quiz_result(
            domain, outcome.result.score, outcome.result.passed
        )
        log.append(
            "Прогресс (training-state.json): {} — счёт {:.2f}, серия {}, "
            "уроков завершено {}".format(
                domain, entry["score"], entry["streak"], entry["completed_lessons"]
            )
        )
        return {
            "quiz_output": outcome.result.feedback,
            "quiz_result": outcome.result.model_dump(),
            "log": log,
        }

    def route_after_route(state: TrainerState) -> str:
        """Map the selected path to the next node (conditional edges)."""
        return state["route"]["path"]

    graph = StateGraph(TrainerState)
    graph.add_node("assess", assess_node)
    graph.add_node("route", route_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("teach", teach_node)
    graph.add_node("quiz", quiz_node)
    graph.add_edge(START, "assess")
    graph.add_edge("assess", "route")
    graph.add_conditional_edges(
        "route",
        route_after_route,
        {
            "knows_it": "quiz",
            "partial": "teach",
            "new_topic": "teach",
            "clarification": "clarify",
        },
    )
    graph.add_edge("clarify", "route")
    graph.add_edge("teach", "quiz")
    graph.add_edge("quiz", END)
    return graph.compile(checkpointer=checkpointer)
