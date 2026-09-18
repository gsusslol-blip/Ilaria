"""Role lock for small local models — packs must not break daughter/member voice."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.packs import get_user_pack_prompt
from jarvis.personality import (
    compact_system_prompt,
    guard_filial_reply,
    messages_with_lock,
    scrub_public_reply,
    sticky_role_card,
)


class RoleLockTests(unittest.TestCase):
    def test_owner_card_allows_papa(self) -> None:
        card = sticky_role_card(is_owner=True, address_as="pá")
        self.assertIn("ILARIA", card.upper())
        self.assertIn("pá", card.lower())
        self.assertNotRegex(card.upper().replace(" ", ""), r"F\.?R\.?I\.?D\.?A\.?Y")

    def test_member_card_forbids_daughter(self) -> None:
        card = sticky_role_card(is_owner=False, address_as="Luis")
        self.assertIn("Luis", card)
        self.assertIn("NUNCA papá", card)

    def test_member_reply_strips_papa(self) -> None:
        out = guard_filial_reply("Hola papá, listo el clima.", is_owner=False, address_as="Luis")
        self.assertNotRegex(out.lower(), r"\bpapá\b")
        self.assertIn("Luis", out)

    def test_owner_reply_keeps_papa(self) -> None:
        out = guard_filial_reply("Hola pá, ya estoy.", is_owner=True, address_as="pá")
        self.assertIn("pá", out.lower())

    def test_identity_leak_stripped(self) -> None:
        # Input simulates a leaked third-party brand claim; scrub must drop it.
        leaked = "Soy " + "JAR" + "VIS.\nAcá el dólar blue."
        out = guard_filial_reply(leaked, is_owner=True, address_as="pá")
        self.assertNotIn("JAR" + "VIS", out.upper())
        self.assertIn("dólar", out.lower())

    def test_pack_prompt_voice_lock(self) -> None:
        block = get_user_pack_prompt(["trading"], current_pack="trading", user_role="owner")
        self.assertIn("VOICE LOCK", block)
        self.assertIn("never rewrite identity", block)
        self.assertIn("TRADING", block)

    def test_compact_prompt_includes_lock_and_pack(self) -> None:
        prompt = compact_system_prompt(
            is_owner=True,
            address_as="pá",
            custom_tone="tierno",
            pack_block="[ACTIVE WORK MODE: TRADING]",
            facts="- ciudad: Buenos Aires",
            journal="backtesting",
            stamp="2026-09-10",
            name="Ilaria",
        )
        self.assertIn("ilaria", prompt.lower())
        self.assertNotIn("f.r.i.d.a.y", prompt.lower())
        self.assertIn("TRADING", prompt)
        self.assertIn("tierno", prompt.lower())
        self.assertLess(len(prompt), 2500)

    def test_lock_glued_to_last_user_not_history(self) -> None:
        original = [{"role": "user", "content": "hola pá"}]
        locked = messages_with_lock(original, is_owner=True)
        self.assertEqual(original[0]["content"], "hola pá")
        self.assertIn("[LOCK:", locked[0]["content"])
        self.assertTrue(locked[0]["content"].startswith("hola pá"))

    def test_scrub_unicode_escapes_and_markdown(self) -> None:
        raw = (
            "La distancia aérea entre la Ciudad\\u202fde\\u202fBuenos\\u202fAires "
            "y Brasilia es de **aprox. 2\\u202f200\\u202fkm**."
        )
        out = scrub_public_reply(raw)
        self.assertNotIn("\\u202f", out)
        self.assertNotIn("**", out)
        self.assertIn("Ciudad de Buenos Aires", out)
        self.assertIn("2200", out.replace(" ", ""))

    def test_scrub_latex_math(self) -> None:
        raw = (
            r"La HJB es \[ \rho V(x)=\sup_{u}\Big\{ f(x,u)+\mathcal{L}^u V(x)\Big\} \] "
            r"con $\sigma$ y $\partial_t$."
        )
        out = scrub_public_reply(raw)
        self.assertNotIn(r"\[", out)
        self.assertNotIn(r"\rho", out)
        self.assertNotIn("$", out)
        self.assertIn("rho", out.lower())


if __name__ == "__main__":
    unittest.main()
