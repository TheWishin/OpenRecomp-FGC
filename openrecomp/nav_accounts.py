"""Controller rows for account maintenance, recovery and blocked players."""
from . import i18n


_SECRET_FIELDS = ("online_current_password", "online_new_password", "online_repeat_password", "online_recovery_code")


def _field(nav, g, field, label, hint):
    row = nav._online_text_item(g, field, label, hint)
    if field in _SECRET_FIELDS:
        row["value"] = i18n.literal("\u2022" * len(g.a.text_value(field)))
    return row


def rows(nav, g, state, action):
    capabilities = state.get("capabilities") or {}
    phase = state.get("phase", "offline")
    out = []
    if phase in ("offline", "error", "kicked") and capabilities.get("account_recovery"):
        out.append(_field(nav, g, "online_fingerprint", "@online120.fingerprint", "@online.login_hint"))
        out.append(dict(kind="heading", label="@online120.recover_account"))
        for field, label in (("online_recovery_code", "@online120.recovery_code"),
                             ("online_new_password", "@online120.new_password"),
                             ("online_repeat_password", "@online120.repeat_password")):
            out.append(_field(nav, g, field, label, "@online120.account_hint"))
        out.append(action("recover_account", "@online120.recover_account", "@online120.account_hint"))
        return out
    if phase != "logged_in":
        return out
    if capabilities.get("account_tools"):
        out.append(dict(kind="heading", label="@online120.account_tools"))
        for field, label in (("online_current_password", "@online120.current_password"),
                             ("online_new_password", "@online120.new_password"),
                             ("online_repeat_password", "@online120.repeat_password")):
            out.append(_field(nav, g, field, label, "@online120.account_hint"))
        out += [action("account_change_password", "@online120.change_password", "@online120.account_hint"),
                action("account_new_codes", "@online120.new_codes", "@online120.account_hint")]
    if capabilities.get("account_blocks"):
        out += [dict(kind="heading", label="@online120.blocks"),
                action("accounts_refresh_blocks", "@online120.refresh_blocks", "@online120.blocks_hint"),
                _field(nav, g, "online_block_name", "@online120.block_name", "@online120.blocks_hint"),
                action("account_block", "@online120.block", "@online120.blocks_hint")]
        for row in state.get("blocks") or []:
            name = row.get("name") or ""
            item = action("account_unblock:" + name, "@online120.unblock", "@online120.blocks_hint")
            item["value"] = i18n.literal(name)
            item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(name))]
            out.append(item)
    return out
