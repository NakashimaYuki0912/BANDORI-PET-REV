import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from llm_manager import CHARACTER_PROMPTS, parse_action_tags, strip_action_tags
from live2d_lua_adapter import LuaLAppModel
import pet_window


class TestArisaShyAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_shy_action_tag_map(self):
        """Verify shy aliases map to 'shy' in tag map."""
        tag_map = pet_window._CHAT_ACTION_TAG_MAP
        self.assertEqual(tag_map.get("shy"), "shy")
        self.assertEqual(tag_map.get("chomama"), "shy")
        self.assertEqual(tag_map.get("tere"), "shy")
        self.assertEqual(tag_map.get("tsundere_shy"), "shy")

    def test_lua_adapter_parameter_methods(self):
        """Verify LAppModel parameter manipulation methods."""
        model = LuaLAppModel(MagicMock())
        model.SetParameterValue("PARAM_CHEEK", 1.0, 1.0)
        model.SetParameterValue("PARAM_EYE_L_OPEN", 0.0, 1.0)
        self.assertIn("PARAM_CHEEK", model._pending_parameters)
        self.assertEqual(model._pending_parameters["PARAM_CHEEK"], ("PARAM_CHEEK", 1.0, 1.0))
        self.assertIn("PARAM_EYE_L_OPEN", model._pending_parameters)

        # Delete single param
        model.DeleteParameterValue("PARAM_EYE_L_OPEN")
        self.assertNotIn("PARAM_EYE_L_OPEN", model._pending_parameters)
        self.assertIn("PARAM_CHEEK", model._pending_parameters)

        # Clear with exclusion
        model.SetParameterValue("PARAM_MOUTH_OPEN_Y", 0.5, 1.0)
        model.ClearParameterValues(exclude={"PARAM_MOUTH_OPEN_Y"})
        self.assertNotIn("PARAM_CHEEK", model._pending_parameters)
        self.assertIn("PARAM_MOUTH_OPEN_Y", model._pending_parameters)

        # Full clear
        model.ClearParameterValues()
        self.assertEqual(len(model._pending_parameters), 0)

    def test_arisa_shy_action_parameter_application(self):
        """Verify PetWindow._on_chat_action('shy') sets closed-eye blushing parameters."""
        mock_model = MagicMock()
        mock_model_setting = MagicMock()
        mock_model_setting.getMotionNames.return_value = ["shame01.mtn", "smile01.mtn"]
        mock_model.modelSetting = mock_model_setting
        mock_model.expressions = {}

        params_set = {}
        def mock_set_param(pid, val, weight=1.0):
            params_set[pid] = val
        mock_model.SetParameterValue.side_effect = mock_set_param

        mock_widget = MagicMock()
        mock_widget.model = mock_model

        window = pet_window.PetWindow.__new__(pet_window.PetWindow)
        window._live2d_widget = mock_widget
        window._current_char = "arisa"
        window._live2d = MagicMock()
        window._note_user_interaction = MagicMock()
        window._schedule_default_expression_restore = MagicMock()
        window._expression_guard_token = 0
        window._motion_guard_token = 0
        window._live2d_idle_actions_enabled = False
        window._custom_action_params = set()
        window._custom_action_param_token = 0

        # Trigger shy action
        window._on_chat_action("shy")

        # Check that blush, closed eyes, and tsundere eyebrow/mouth parameters were set
        self.assertIn("PARAM_CHEEK", params_set)
        self.assertEqual(params_set["PARAM_CHEEK"], 1.0)
        self.assertIn("PARAM_CHEEK2", params_set)
        self.assertEqual(params_set["PARAM_CHEEK2"], 1.0)
        self.assertIn("PARAM_EYE_L_OPEN", params_set)
        self.assertEqual(params_set["PARAM_EYE_L_OPEN"], 0.0)
        self.assertIn("PARAM_EYE_R_OPEN", params_set)
        self.assertEqual(params_set["PARAM_EYE_R_OPEN"], 0.0)
        self.assertIn("PARAM_EYE_L_SMILE", params_set)
        self.assertEqual(params_set["PARAM_EYE_L_SMILE"], 1.0)
        self.assertIn("PARAM_BROW_L_FORM", params_set)
        self.assertEqual(params_set["PARAM_BROW_L_FORM"], -1.0)

        # Check motion was started
        mock_model.StartMotion.assert_called_once()
        started_motion = mock_model.StartMotion.call_args[0][0]
        self.assertEqual(started_motion, "shame01.mtn")

        # Test cleanup
        deleted_params = set()
        def mock_del_param(pid):
            deleted_params.add(pid)
        mock_model.DeleteParameterValue.side_effect = mock_del_param

        window._clear_custom_action_parameters()
        self.assertEqual(len(window._custom_action_params), 0)
        self.assertTrue(deleted_params.issuperset({"PARAM_CHEEK", "PARAM_EYE_L_OPEN", "PARAM_EYE_L_SMILE"}))

    def test_arisa_prompt_shy_and_praise_rules(self):
        """Verify Arisa's system prompt specifies tsundere shy praise reaction and [shy] tag."""
        prompt = CHARACTER_PROMPTS.get("arisa", "")
        self.assertTrue(len(prompt) > 0)
        self.assertIn("【害羞与夸奖反应】", prompt)
        self.assertIn("[shy]", prompt)
        self.assertIn("ちょ、ちょっと！", prompt)
        self.assertIn("夸奖", prompt)

        # Test action parsing
        tags = parse_action_tags("ちょ、ちょっと！谁允许你突然夸我可爱了啊！[shy]")
        self.assertIn("shy", tags)
        cleaned = strip_action_tags("ちょ、ちょっと！谁允许你突然夸我可爱了啊！[shy]")
        self.assertEqual(cleaned, "ちょ、ちょっと！谁允许你突然夸我可爱了啊！")

    def test_arisa_shy_action_chained_linkage(self):
        """Verify 2-stage action linkage: Stage 1 (shame02 + flustered wide eyes) -> Stage 2 (shame01 + demure closed eyes)."""
        mock_model = MagicMock()
        mock_model_setting = MagicMock()
        mock_model_setting.getMotionNames.return_value = ["shame01.mtn", "shame02.mtn", "smile01.mtn"]
        mock_model.modelSetting = mock_model_setting
        mock_model.expressions = {}

        params_set = {}
        def mock_set_param(pid, val, weight=1.0):
            params_set[pid] = val
        mock_model.SetParameterValue.side_effect = mock_set_param

        mock_widget = MagicMock()
        mock_widget.model = mock_model

        window = pet_window.PetWindow.__new__(pet_window.PetWindow)
        window._live2d_widget = mock_widget
        window._current_char = "arisa"
        window._live2d = MagicMock()
        window._note_user_interaction = MagicMock()
        window._schedule_default_expression_restore = MagicMock()
        window._expression_guard_token = 0
        window._motion_guard_token = 0
        window._live2d_idle_actions_enabled = False
        window._custom_action_params = set()
        window._custom_action_param_token = 0
        window._action_chain_token = 0

        # Trigger shy action
        window._on_chat_action("shy")

        # Stage 1 assertions: shame02 started immediately
        mock_model.StartMotion.assert_called_once()
        started_motion_stage1 = mock_model.StartMotion.call_args[0][0]
        self.assertEqual(started_motion_stage1, "shame02.mtn")

        # Stage 1 parameters: startled wide eyes, eyebrow frown, initial blush
        self.assertIn("PARAM_EYE_L_OPEN", params_set)
        self.assertEqual(params_set["PARAM_EYE_L_OPEN"], 1.25)
        self.assertIn("PARAM_EYE_R_OPEN", params_set)
        self.assertEqual(params_set["PARAM_EYE_R_OPEN"], 1.25)
        self.assertIn("PARAM_CHEEK", params_set)
        self.assertEqual(params_set["PARAM_CHEEK"], 0.85)
        self.assertIn("PARAM_BROW_L_ANGLE", params_set)
        self.assertEqual(params_set["PARAM_BROW_L_ANGLE"], 0.35)
        self.assertIn("PARAM_MOUTH_FORM_01", params_set)
        self.assertEqual(params_set["PARAM_MOUTH_FORM_01"], -0.8)

        # Stage 2 execution
        stage2_params = {
            "PARAM_EYE_L_OPEN": 0.0,
            "PARAM_EYE_R_OPEN": 0.0,
            "PARAM_EYE_L_SMILE": 1.0,
            "PARAM_EYE_R_SMILE": 1.0,
            "PARAM_BROW_L_ANGLE": 0.45,
            "PARAM_BROW_R_ANGLE": 0.45,
            "PARAM_BROW_L_FORM": -1.0,
            "PARAM_BROW_R_FORM": -1.0,
            "PARAM_BROW_L_Y": -0.6,
            "PARAM_BROW_R_Y": -0.6,
            "PARAM_CHEEK": 1.0,
            "PARAM_CHEEK2": 1.0,
            "PARAM_MOUTH_FORM_01": -1.0,
            "PARAM_MOUTH_SCALE": -0.3,
        }
        window._execute_chained_action_stage2(
            window._action_chain_token,
            window._motion_guard_token,
            "shame01.mtn",
            stage2_params,
        )

        # Stage 2 assertions: shame01 started
        self.assertEqual(mock_model.StartMotion.call_count, 2)
        started_motion_stage2 = mock_model.StartMotion.call_args[0][0]
        self.assertEqual(started_motion_stage2, "shame01.mtn")

        # Stage 2 parameters: closed eyes in smiling squint, full blush
        self.assertEqual(params_set["PARAM_EYE_L_OPEN"], 0.0)
        self.assertEqual(params_set["PARAM_EYE_R_OPEN"], 0.0)
        self.assertEqual(params_set["PARAM_EYE_L_SMILE"], 1.0)
        self.assertEqual(params_set["PARAM_CHEEK"], 1.0)
        self.assertEqual(params_set["PARAM_BROW_L_FORM"], -1.0)

        # Test cleanup
        deleted_params = set()
        mock_model.DeleteParameterValue.side_effect = lambda pid: deleted_params.add(pid)
        window._clear_custom_action_parameters()
        self.assertEqual(len(window._custom_action_params), 0)
        self.assertTrue(deleted_params.issuperset({"PARAM_CHEEK", "PARAM_EYE_L_OPEN", "PARAM_EYE_L_SMILE"}))

    def test_arisa_shy_action_interruption_guard(self):
        """Verify that user interaction or interruption invalidates pending Stage 2 chained motion."""
        mock_model = MagicMock()
        mock_model_setting = MagicMock()
        mock_model_setting.getMotionNames.return_value = ["shame01.mtn", "shame02.mtn"]
        mock_model.modelSetting = mock_model_setting
        mock_model.expressions = {}

        mock_widget = MagicMock()
        mock_widget.model = mock_model

        window = pet_window.PetWindow.__new__(pet_window.PetWindow)
        window._live2d_widget = mock_widget
        window._current_char = "arisa"
        window._live2d = MagicMock()
        window._note_user_interaction = MagicMock()
        window._schedule_default_expression_restore = MagicMock()
        window._expression_guard_token = 0
        window._motion_guard_token = 0
        window._live2d_idle_actions_enabled = False
        window._custom_action_params = set()
        window._custom_action_param_token = 0
        window._action_chain_token = 0

        window._on_chat_action("shy")
        self.assertEqual(mock_model.StartMotion.call_count, 1)

        saved_chain_token = window._action_chain_token
        saved_motion_token = window._motion_guard_token

        # Simulate user click / token change before Stage 2 fires
        window._motion_guard_token += 1

        # Attempt to fire Stage 2 with stale tokens
        window._execute_chained_action_stage2(
            saved_chain_token,
            saved_motion_token,
            "shame01.mtn",
            {"PARAM_CHEEK": 1.0},
        )

        # StartMotion should NOT have been called a second time
        self.assertEqual(mock_model.StartMotion.call_count, 1)

    def test_arisa_shy_action_lip_sync_isolation(self):
        """Verify that neither stage of shy action touches PARAM_MOUTH_OPEN_Y and cleanup preserves lip sync."""
        mock_model = MagicMock()
        mock_model_setting = MagicMock()
        mock_model_setting.getMotionNames.return_value = ["shame01.mtn", "shame02.mtn"]
        mock_model.modelSetting = mock_model_setting
        mock_model.expressions = {}

        touched_params = set()
        mock_model.SetParameterValue.side_effect = lambda pid, val, weight=1.0: touched_params.add(pid)
        deleted_params = set()
        mock_model.DeleteParameterValue.side_effect = lambda pid: deleted_params.add(pid)

        mock_widget = MagicMock()
        mock_widget.model = mock_model

        window = pet_window.PetWindow.__new__(pet_window.PetWindow)
        window._live2d_widget = mock_widget
        window._current_char = "arisa"
        window._live2d = MagicMock()
        window._note_user_interaction = MagicMock()
        window._schedule_default_expression_restore = MagicMock()
        window._expression_guard_token = 0
        window._motion_guard_token = 0
        window._live2d_idle_actions_enabled = False
        window._custom_action_params = set()
        window._custom_action_param_token = 0
        window._action_chain_token = 0

        # Stage 1
        window._on_chat_action("shy")
        self.assertNotIn("PARAM_MOUTH_OPEN_Y", touched_params)

        # Stage 2
        window._execute_chained_action_stage2(
            window._action_chain_token,
            window._motion_guard_token,
            "shame01.mtn",
            {"PARAM_CHEEK": 1.0, "PARAM_EYE_L_OPEN": 0.0},
        )
        self.assertNotIn("PARAM_MOUTH_OPEN_Y", touched_params)

        # Cleanup
        window._clear_custom_action_parameters()
        self.assertNotIn("PARAM_MOUTH_OPEN_Y", deleted_params)

    def test_multichar_shy_fallback(self):
        """Verify graceful fallback for characters/outfits with single motion or no shame motion."""
        mock_model = MagicMock()
        mock_model_setting = MagicMock()
        mock_model.modelSetting = mock_model_setting
        mock_model.expressions = {}

        mock_widget = MagicMock()
        mock_widget.model = mock_model

        window = pet_window.PetWindow.__new__(pet_window.PetWindow)
        window._live2d_widget = mock_widget
        window._live2d = MagicMock()
        window._note_user_interaction = MagicMock()
        window._schedule_default_expression_restore = MagicMock()
        window._expression_guard_token = 0
        window._motion_guard_token = 0
        window._live2d_idle_actions_enabled = False
        window._custom_action_params = set()
        window._custom_action_param_token = 0
        window._action_chain_token = 0

        # Case 1: Kasumi with only shame01.mtn -> single-stage shame01.mtn
        window._current_char = "kasumi"
        mock_model_setting.getMotionNames.return_value = ["kasumi_shame01.mtn", "kasumi_smile01.mtn"]
        window._on_chat_action("shy")
        self.assertEqual(mock_model.StartMotion.call_count, 1)
        self.assertEqual(mock_model.StartMotion.call_args[0][0], "kasumi_shame01.mtn")

        # Case 2: Mashiro with no shame motions -> falls back to smile01.mtn
        mock_model.StartMotion.reset_mock()
        window._current_char = "mashiro"
        mock_model_setting.getMotionNames.return_value = ["mashiro_smile01.mtn", "mashiro_idle01.mtn"]
        window._on_chat_action("shy")
        self.assertEqual(mock_model.StartMotion.call_count, 1)
        self.assertEqual(mock_model.StartMotion.call_args[0][0], "mashiro_smile01.mtn")


if __name__ == "__main__":
    unittest.main()
