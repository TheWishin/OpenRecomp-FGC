"""Account maintenance and blocking through the selected install's lobby client."""
from .t5_online import close_client


_SECRETS = ("online_current_password", "online_new_password", "online_repeat_password", "online_recovery_code")


def init(owner):
    if hasattr(owner, "_account_blocks"):
        return
    owner._account_blocks = []
    for field in (*_SECRETS, "online_block_name"):
        owner._online_fields.setdefault(field, "")
    owner._online_fields.setdefault("online_fingerprint", str(owner._online_config().get("fingerprint") or ""))


def state(owner):
    init(owner)
    client = owner._online_client
    account = bool(owner._online_account)
    return dict(capabilities=dict(
        account_tools=bool(account and client and callable(getattr(client, "change_password", None))
                           and callable(getattr(client, "new_recovery_codes", None))),
        account_blocks=bool(client and all(callable(getattr(client, method, None))
                                          for method in ("blocks", "block", "unblock"))),
        account_recovery=True),
        blocks=[dict(row) for row in owner._account_blocks])


def _clear_secrets(owner):
    for field in _SECRETS:
        owner._online_fields[field] = ""


def _new_password(owner):
    password = owner._online_fields["online_new_password"]
    repeated = owner._online_fields["online_repeat_password"]
    return password if 6 <= len(password) <= 128 and password == repeated else None


def offline_action(owner, operation):
    if operation != "recover_account":
        return False
    init(owner)
    if owner._online_phase not in ("offline", "error", "kicked") or owner._online_client is not None:
        return True
    name = owner._online_fields["online_name"].strip()
    code = owner._online_fields["online_recovery_code"].strip()
    password = _new_password(owner)
    _clear_secrets(owner)
    if not name or not code or password is None:
        owner._online_message = "@online120.password_invalid"
        return True
    generation = owner._online_generation
    server = owner._online_fields["online_server"].strip()
    owner._online_phase, owner._online_message = "connecting", "@online.connecting"

    def work():
        client = None
        try:
            client, _target = owner._online_new_client(server)
            with owner._online_lock:
                if generation != owner._online_generation:
                    raise RuntimeError("@online.cancelled")
            client.connect()
            with owner._online_lock:
                if generation != owner._online_generation:
                    raise RuntimeError("@online.cancelled")
            result = client.recover(name, code, password)
            return dict(name=str(result.get("name") or name)[:64]) if isinstance(result, dict) else dict(name=name[:64])
        finally:
            if client is not None:
                close_client(client)

    owner._online_submit("feature_accounts:recover", work)
    return True


def action(owner, operation, client):
    init(owner)
    known = operation in ("account_change_password", "account_new_codes", "accounts_refresh_blocks", "account_block")
    if not known and not operation.startswith("account_unblock:"):
        return False
    if owner._online_phase != "logged_in" or owner._online_busy:
        return True
    capabilities = state(owner)["capabilities"]
    generation = owner._online_generation
    if operation in ("account_change_password", "account_new_codes"):
        if not capabilities["account_tools"]:
            return True
        old = owner._online_fields["online_current_password"]
        password = _new_password(owner)
        _clear_secrets(owner)
        if not old or (operation == "account_change_password" and password is None):
            owner._online_message = "@online120.password_invalid"
            return True

        def work():
            owner._online_check_request(generation, client)
            if operation == "account_new_codes":
                return client.new_recovery_codes(old)
            previous = getattr(client, "session", None)
            client.change_password(old, password, remember=True)
            with owner._online_lock:
                owner._online_check_request(generation, client)
                try:
                    owner._online_write_session(owner._online_fields["online_server"], owner._online_name,
                                                getattr(client, "session", None), expected=previous)
                except (OSError, ValueError, TypeError):
                    return "@online.save_failed"
            return "@online120.password_changed"

        verb = "codes" if operation == "account_new_codes" else "password"
    else:
        if not capabilities["account_blocks"]:
            return True
        name = (operation.partition(":")[2] if operation.startswith("account_unblock:")
                else owner._online_fields["online_block_name"].strip())
        if operation == "account_block" and not name:
            return True
        if operation.startswith("account_unblock:") and not any(row["name"] == name for row in owner._account_blocks):
            return True

        def work():
            owner._online_check_request(generation, client)
            if operation == "account_block":
                client.block(name)
            elif operation.startswith("account_unblock:"):
                client.unblock(name)
            owner._online_check_request(generation, client)
            return client.blocks()

        verb = "blocks"
    owner._online_submit("feature_accounts:" + verb, work)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith("feature_accounts:"):
        return False
    if operation == "feature_accounts:recover":
        owner._online_phase = "offline"
    if error:
        owner._online_message = owner._online_error(error)
    elif operation == "feature_accounts:codes":
        owner._online_recovery_codes = [code[:64] for code in value[:32] if isinstance(code, str)] if isinstance(value, (list, tuple)) else []
        owner._online_message = "@online.recovery_hint"
    elif operation == "feature_accounts:password":
        owner._online_message = value
    elif operation == "feature_accounts:recover":
        owner._online_fields["online_name"] = value["name"]
        owner._online_name_prefill = False
        owner._online_message = "@online120.recovered"
    elif operation == "feature_accounts:blocks":
        owner._account_blocks = [dict(name=str(row["name"])[:64], guest=bool(row.get("guest")))
                                 for row in value[:200] if isinstance(row, dict) and isinstance(row.get("name"), str)] if isinstance(value, list) else []
        owner._online_fields["online_block_name"] = ""
        owner._online_message = "@online120.block_updated"
    return True


def event(owner, event):
    return False


def reset(owner):
    init(owner)
    owner._account_blocks = []
    owner._online_fields["online_block_name"] = ""
    _clear_secrets(owner)
