from loguru import logger

from core.input.input_validator import InputValidator
from core.input_controller import InputController
from core.nlp.normalizer import normalize_text
from core.nlp.intent import Intent
from core.context.short_term import ShortTermContext
from core.context.long_term import save_message
from core.intelligence.intent_scorer import score_intents, pick_best_intent
from core.intelligence.confidence_refiner import refine_confidence
from core.actions.action_executor import ActionExecutor

from core.control.global_interrupt import GLOBAL_INTERRUPT
from core.control.interrupt_words import INTERRUPT_KEYWORDS
from core.control.interrupt_policy import INTERRUPT_POLICY

from core.memory.context_pack import ContextPackBuilder
from core.memory.follow_up_resolver import FollowUpResolver
from core.memory.short_term_memory import ShortTermMemory

# 🔐 Permissions
from core.os.permission.consent_store import ConsentStore
from core.os.permission.permission_registry import PermissionRegistry

# 🔊 Optional TTS
from core.output.tts.tts_registry import TTSEngineRegistry


INTENT_CONFIDENCE_THRESHOLD = 0.65

CLARIFICATION_MESSAGES = [
    "I didn’t understand that. Please rephrase.",
    "Can you clarify what you want to do?",
    "That wasn’t clear. Try again.",
]

IDLE, ACTIVE = "idle", "active"

NEGATION_TOKENS = {"dont", "do", "not", "never", "no"}
AFFIRMATIVE = {"yes", "yeah", "yep", "sure", "ok"}
NEGATIVE = {"no", "nope", "nah"}


class Assistant:
    def __init__(self):
        self.input = InputController()
        self.input_validator = InputValidator()
        self.action_executor = ActionExecutor()

        self.ctx = ShortTermContext()
        self.stm = ShortTermMemory()
        self.consent_store = ConsentStore()

        self.running = True
        self.state = IDLE
        self.clarify_index = 0

        # 🔊 TTS (optional, fail-safe)
        self.tts_engine = TTSEngineRegistry.get_default()

    # =================================================
    # UTIL
    # =================================================
    def _next_clarification(self) -> str:
        msg = CLARIFICATION_MESSAGES[self.clarify_index]
        self.clarify_index = (self.clarify_index + 1) % len(CLARIFICATION_MESSAGES)
        return msg

    def _get_interrupt_policy(self, intent: Intent | None) -> str:
        if not intent:
            return "HARD"
        return INTERRUPT_POLICY.get(intent, "HARD")

    # =================================================
    # INTERRUPT DETECTION
    # =================================================
    def _detect_embedded_interrupt(self, tokens: list[str]) -> bool:
        for i, token in enumerate(tokens):
            if token in INTERRUPT_KEYWORDS:
                if i > 0 and tokens[i - 1] in NEGATION_TOKENS:
                    return False
                return True
        return False

    def _handle_interrupt(self, source: str, intent: Intent | None):
        policy = self._get_interrupt_policy(intent)
        logger.warning(f"Interrupt triggered ({source}) | policy={policy}")

        if policy == "IGNORE":
            return

        GLOBAL_INTERRUPT.trigger()
        self.action_executor.cancel_pending()
        self.input.reset_execution_state()

        print("Karn > Execution stopped.")
        if self.tts_engine:
            self.tts_engine.speak("Execution stopped.")

        GLOBAL_INTERRUPT.clear()

    # =================================================
    # PERMISSION HANDLING
    # =================================================
    def _handle_permission_request(self, intent: Intent) -> bool:
        scopes = PermissionRegistry.get_required_scopes(intent.value)
        if not scopes:
            return True

        scope_list = ", ".join(scopes)
        prompt = f"This action requires permission: {scope_list}. Allow?"

        print(f"Karn > {prompt}")
        if self.tts_engine:
            self.tts_engine.speak(prompt)

        reply = self.input.read().strip().lower()
        tokens = set(normalize_text(reply))

        if tokens & AFFIRMATIVE:
            for scope in scopes:
                self.consent_store.grant(scope)
            return True

        print("Karn > Permission denied.")
        if self.tts_engine:
            self.tts_engine.speak("Permission denied.")

        return False

    # =================================================
    # CORE LOOP (SINGLE CYCLE)
    # =================================================
    def _cycle(self):
        context_pack = ContextPackBuilder().build()
        context_pack["stm_recent"] = self.stm.fetch_recent(
            role="user", limit=3, min_confidence=0.7
        )

        raw_text = self.input.read()
        if not raw_text:
            return

        validation = self.input_validator.validate(raw_text)
        if not validation["valid"]:
            print("Karn > Please repeat.")
            return

        clean_text = validation["clean_text"]
        tokens = normalize_text(clean_text)

        if self._detect_embedded_interrupt(tokens):
            self._handle_interrupt("embedded", None)
            return

        scores = score_intents(tokens)
        intent, confidence = pick_best_intent(scores, tokens)

        confidence = refine_confidence(
            confidence, tokens, intent.value, self.ctx.last_intent
        )

        if confidence < INTENT_CONFIDENCE_THRESHOLD or intent == Intent.UNKNOWN:
            resolved = FollowUpResolver().resolve(tokens, context_pack)
            if not resolved:
                print(self._next_clarification())
                return
            intent = Intent(resolved["resolved_intent"])
            confidence = 0.7

        save_message("user", clean_text, intent.value)

        if intent == Intent.EXIT:
            print("Karn > Shutting down.")
            if self.tts_engine:
                self.tts_engine.speak("Shutting down.")
            self.running = False
            return

        if not self._handle_permission_request(intent):
            return

        result = self.action_executor.execute(intent, clean_text, confidence)
        response = result.get("message", "Done.")

        print(f"Karn > {response}")
        if self.tts_engine:
            self.tts_engine.speak(response)

        save_message("assistant", response, intent.value)
        self.ctx.update(intent.value)

    # =================================================
    # RUNNERS
    # =================================================
    def run(self):
        logger.info("Karn Assistant started — core online")
        while self.running:
            self._cycle()

    def run_once(self):
        self._cycle()
