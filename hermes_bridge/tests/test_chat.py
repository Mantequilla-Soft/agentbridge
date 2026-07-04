from __future__ import annotations

from hermes_bridge.client.chat import Target, format_message


def room_msg(target="general", sender="alice"):
    return {"id": 1, "sender": sender, "target_type": "room", "target": target, "body": "hi", "file": None}


def dm_msg(sender, target):
    return {"id": 2, "sender": sender, "target_type": "dm", "target": target, "body": "hi", "file": None}


def test_room_target_matches_same_room_only():
    target = Target("room", "general")
    assert target.matches(room_msg(target="general"), my_name="alice")
    assert not target.matches(room_msg(target="random"), my_name="alice")
    assert not target.matches(dm_msg("alice", "bob"), my_name="alice")


def test_dm_target_matches_either_direction():
    target = Target("dm", "bob")
    assert target.matches(dm_msg(sender="alice", target="bob"), my_name="alice")
    assert target.matches(dm_msg(sender="bob", target="alice"), my_name="alice")
    assert not target.matches(dm_msg(sender="bob", target="carol"), my_name="alice")
    assert not target.matches(room_msg(), my_name="alice")


def test_dm_target_ignores_unrelated_third_party_dm():
    target = Target("dm", "bob")
    assert not target.matches(dm_msg(sender="carol", target="dave"), my_name="alice")


def test_format_message_includes_file_note_when_present():
    m = {"id": 5, "sender": "bob", "body": "here", "file": {"filename": "x.zip", "id": 9}}
    assert "x.zip" in format_message(m)
    assert "id=9" in format_message(m)


def test_format_message_omits_file_note_when_absent():
    m = {"id": 5, "sender": "bob", "body": "here", "file": None}
    assert "file:" not in format_message(m)
