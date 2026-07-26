import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent

def test_launchd_recovery_plists_keepalive():
    """Verify launchd plists have KeepAlive set to true for crash recovery."""
    import plistlib
    
    intake_plist = KIT_ROOT / "launchd" / "com.gddp.intake.plist"
    heartbeat_plist = KIT_ROOT / "launchd" / "com.gddp.heartbeat.plist"
    
    with intake_plist.open("rb") as f:
        intake = plistlib.load(f)
        assert intake.get("KeepAlive") is True, "intake launchd missing KeepAlive=true"
        
    with heartbeat_plist.open("rb") as f:
        heartbeat = plistlib.load(f)
        # Heartbeat is a cron, it uses StartInterval rather than KeepAlive
        assert "StartInterval" in heartbeat, "heartbeat launchd missing StartInterval"
        assert not heartbeat.get("KeepAlive"), "heartbeat should not be KeepAlive (it is a cron task)"
