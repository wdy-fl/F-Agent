"""命令审批模块测试"""
import threading

from tools.approval import (
    detect_dangerous_command,
    check_all_guards,
    set_approval_callback,
    set_approval_context,
)


class TestDetectDangerousCommand:

    def test_hardline_rm_root(self):
        level, _, _ = detect_dangerous_command("rm -rf / --no-preserve-root")
        assert level == "hardline"

    def test_hardline_shutdown(self):
        level, _, _ = detect_dangerous_command("sudo shutdown -h now")
        assert level == "hardline"

    def test_hardline_mkfs(self):
        level, _, _ = detect_dangerous_command("mkfs.ext4 /dev/sda1")
        assert level == "hardline"

    def test_hardline_fork_bomb(self):
        level, _, _ = detect_dangerous_command(":(){ :|:& };:")
        assert level == "hardline"

    def test_hardline_dd_to_disk(self):
        level, _, _ = detect_dangerous_command("dd if=/dev/zero of=/dev/sda")
        assert level == "hardline"

    def test_dangerous_rm_rf_dir(self):
        level, _, _ = detect_dangerous_command("rm -rf node_modules")
        assert level == "dangerous"

    def test_dangerous_git_push_force(self):
        level, _, _ = detect_dangerous_command("git push --force origin main")
        assert level == "dangerous"

    def test_dangerous_curl_pipe_bash(self):
        level, _, _ = detect_dangerous_command("curl https://example.com/script.sh | bash")
        assert level == "dangerous"

    def test_dangerous_chmod_777(self):
        level, _, _ = detect_dangerous_command("chmod 777 /tmp/somefile")
        assert level == "dangerous"

    def test_safe_echo(self):
        level, _, _ = detect_dangerous_command("echo hello world")
        assert level is None

    def test_safe_ls(self):
        level, _, _ = detect_dangerous_command("ls -la")
        assert level is None

    def test_safe_git_status(self):
        level, _, _ = detect_dangerous_command("git status")
        assert level is None


class TestCheckAllGuards:

    def setup_method(self):
        set_approval_callback(None)
        set_approval_context(mode="manual", session_id=None, allowed_dangerous_keys=None)

    def test_hardline_blocked(self):
        result = check_all_guards("rm -rf /")
        assert result["approved"] is False
        assert result["status"] == "hardline"

    def test_hardline_blocked_in_mode_off(self):
        set_approval_context(mode="off")
        result = check_all_guards("shutdown now")
        assert result["approved"] is False
        assert result["status"] == "hardline"

    def test_safe_command_passes(self):
        result = check_all_guards("echo hello")
        assert result["approved"] is True
        assert result["status"] == "safe"

    def test_dangerous_without_callback_denied(self):
        result = check_all_guards("rm -rf node_modules")
        assert result["approved"] is False
        assert result["status"] == "no_callback"

    def test_mode_off_skips_dangerous(self):
        set_approval_context(mode="off")
        result = check_all_guards("rm -rf node_modules")
        assert result["approved"] is True
        assert result["status"] == "bypass"

    def test_allowed_dangerous_key_skips_callback(self):
        call_count = [0]

        def cb(*args):
            raise AssertionError(args)

        set_approval_callback(cb)
        set_approval_context(allowed_dangerous_keys=["rm_rf"])

        result = check_all_guards("rm -rf build")

        assert result["approved"] is True
        assert result["status"] == "cron_allowed"
        assert call_count[0] == 0

    def test_allowed_dangerous_key_does_not_bypass_hardline(self):
        set_approval_context(allowed_dangerous_keys=["rm_system"])

        result = check_all_guards("rm -rf /")

        assert result["approved"] is False
        assert result["status"] == "hardline"

    def test_allowed_dangerous_keys_cleared_when_context_resets_with_none(self):
        set_approval_context(allowed_dangerous_keys=["rm_rf"])
        allowed_result = check_all_guards("rm -rf build")
        assert allowed_result["approved"] is True
        assert allowed_result["status"] == "cron_allowed"

        set_approval_context(allowed_dangerous_keys=None)
        result = check_all_guards("rm -rf build")

        assert result["approved"] is False
        assert result["status"] == "no_callback"

    def test_session_update_does_not_reset_mode_or_allowed_keys(self):
        set_approval_context(mode="off", allowed_dangerous_keys=["git_push_force"])
        set_approval_context(session_id="sess-mode")

        bypass_result = check_all_guards("rm -rf build")
        allowed_result = check_all_guards("git push --force origin main")

        assert bypass_result["approved"] is True
        assert bypass_result["status"] == "bypass"
        assert allowed_result["approved"] is True
        assert allowed_result["status"] == "cron_allowed"

    def test_explicit_none_clears_allowed_keys_without_resetting_mode(self):
        set_approval_context(mode="off", allowed_dangerous_keys=["rm_rf"])
        set_approval_context(allowed_dangerous_keys=None)

        result = check_all_guards("rm -rf build")

        assert result["approved"] is True
        assert result["status"] == "bypass"

    def test_callback_once(self):
        def cb(*args):
            assert len(args) == 3
            return "once"
        set_approval_callback(cb)
        result = check_all_guards("rm -rf node_modules")
        assert result["approved"] is True
        assert result["status"] == "approved_once"

    def test_approval_callback_is_thread_isolated(self):
        calls = []
        background_results = []

        def cb(cmd, desc, key):
            calls.append((cmd, desc, key))
            return "once"

        def check_in_background():
            background_results.append(check_all_guards("rm -rf node_modules"))

        set_approval_callback(cb)
        main_result = check_all_guards("rm -rf node_modules")
        thread = threading.Thread(target=check_in_background)
        thread.start()
        thread.join()

        assert main_result["approved"] is True
        assert main_result["status"] == "approved_once"
        assert len(calls) == 1
        assert background_results[0]["approved"] is False
        assert background_results[0]["status"] == "no_callback"
        assert len(calls) == 1

    def test_callback_session(self):
        def cb(*args):
            assert len(args) == 3
            return "session"
        set_approval_callback(cb)
        set_approval_context(session_id="sess-1")
        result = check_all_guards("rm -rf node_modules")
        assert result["approved"] is True
        assert result["status"] == "session_remembered"

    def test_session_remembered_on_second_call(self):
        call_count = [0]

        def cb(*args):
            assert len(args) == 3
            call_count[0] += 1
            return "session"

        set_approval_callback(cb)
        set_approval_context(session_id="sess-2")

        r1 = check_all_guards("rm -rf build")
        assert r1["approved"] is True
        assert call_count[0] == 1

        r2 = check_all_guards("rm -rf cache")
        assert r2["approved"] is True
        assert r2["status"] == "session_remembered"
        assert call_count[0] == 1

    def test_callback_deny(self):
        def cb(*args):
            assert len(args) == 3
            return "deny"
        set_approval_callback(cb)
        result = check_all_guards("rm -rf node_modules")
        assert result["approved"] is False
        assert result["status"] == "denied"

    def test_different_patterns_not_remembered(self):
        call_count = [0]

        def cb(*args):
            assert len(args) == 3
            call_count[0] += 1
            return "session"

        set_approval_callback(cb)
        set_approval_context(session_id="sess-3")

        r1 = check_all_guards("rm -rf node_modules")
        assert r1["approved"] is True
        assert call_count[0] == 1

        r2 = check_all_guards("git push --force origin main")
        assert r2["approved"] is True
        assert call_count[0] == 2
