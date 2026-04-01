import os
from dataclasses import dataclass
from typing import Optional, Sequence


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULT_INTERNAL_BASE = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"
_DEFAULT_INTERNAL_MODEL = "glm-5"
_DEFAULT_PUBLIC_BASE = "https://api.deepseek.com/v1"
_DEFAULT_PUBLIC_MODEL = "deepseek-reasoner"
_DEFAULT_MOONSHOT_BASE = "https://api.moonshot.cn/v1"
_DEFAULT_MOONSHOT_MODEL = "kimi-k2.5"
_DEFAULT_INTERNAL_TEMPLATE_URL = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"

_ENV_LOADED = False


@dataclass(frozen=True)
class LLMProviderConfig:
    access_code: str
    primary_api_key: str
    primary_api_base: str
    primary_model: str
    backup_api_key: str
    backup_api_base: str
    backup_model: str
    internal_template_url: str
    verify_ssl: bool
    default_temperature: float
    default_max_tokens: int
    default_stream: bool


@dataclass(frozen=True)
class DifyWorkflowConfig:
    api_base: str
    api_key: str
    query_key: str
    context_key: str
    user_prefix: str
    timeout: float
    response_mode: str
    enabled: bool


def _looks_like_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return _looks_like_truthy(raw)


def _candidate_env_paths(additional_roots: Optional[Sequence[str]] = None) -> Sequence[str]:
    roots = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        PROJECT_ROOT,
    ]
    if additional_roots:
        roots.extend([str(root) for root in additional_roots if root])

    seen = set()
    candidates = []
    for root in roots:
        if not root:
            continue
        env_path = root if os.path.basename(root).startswith(".env") else os.path.join(root, ".env")
        env_path = os.path.abspath(env_path)
        if env_path in seen:
            continue
        seen.add(env_path)
        candidates.append(env_path)
    return candidates


def load_workspace_env(additional_roots: Optional[Sequence[str]] = None) -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    try:
        from dotenv import load_dotenv

        load_dotenv()
        _ENV_LOADED = True
        return
    except Exception:
        pass

    for env_path in _candidate_env_paths(additional_roots=additional_roots):
        try:
            if not os.path.exists(env_path):
                continue
            with open(env_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            continue

    _ENV_LOADED = True


def load_llm_provider_config(
    *,
    hardcoded_access_code: str = "",
    hardcoded_api_key: str = "",
    hardcoded_api_base: str = "",
    hardcoded_model: str = "",
    hardcoded_backup_api_key: str = "",
    hardcoded_backup_api_base: str = "",
    hardcoded_backup_model: str = "",
    default_internal_base: str = _DEFAULT_INTERNAL_BASE,
    default_internal_model: str = _DEFAULT_INTERNAL_MODEL,
    default_public_base: str = _DEFAULT_PUBLIC_BASE,
    default_public_model: str = _DEFAULT_PUBLIC_MODEL,
    default_moonshot_base: str = _DEFAULT_MOONSHOT_BASE,
    default_moonshot_model: str = _DEFAULT_MOONSHOT_MODEL,
    default_internal_template_url: str = _DEFAULT_INTERNAL_TEMPLATE_URL,
) -> LLMProviderConfig:
    load_workspace_env()

    access_code = os.environ.get("DEEPSEEK_ACCESS_CODE", "") or hardcoded_access_code

    env_api_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_api_key:
        primary_api_key = env_api_key
    elif access_code:
        primary_api_key = f"ACCESSCODE {access_code}"
    else:
        primary_api_key = hardcoded_api_key

    env_api_base = os.environ.get("DEEPSEEK_API_BASE")
    if env_api_base:
        primary_api_base = env_api_base
    elif hardcoded_api_base:
        primary_api_base = hardcoded_api_base
    else:
        primary_api_base = default_public_base if primary_api_key.startswith("sk-") else default_internal_base

    env_model = os.environ.get("DEEPSEEK_MODEL")
    if env_model:
        primary_model = env_model
    elif hardcoded_model:
        primary_model = hardcoded_model
    else:
        primary_model = default_public_model if primary_api_key.startswith("sk-") else default_internal_model

    moonshot_backup_key = os.environ.get("MOONSHOT_API_KEY_BACKUP")
    backup_api_key = (
        moonshot_backup_key
        or os.environ.get("DEEPSEEK_API_KEY_BACKUP")
        or hardcoded_backup_api_key
    )

    default_backup_base = default_moonshot_base if moonshot_backup_key else default_public_base
    backup_api_base = (
        os.environ.get("MOONSHOT_API_BASE_BACKUP")
        or os.environ.get("DEEPSEEK_API_BASE_BACKUP")
        or hardcoded_backup_api_base
        or default_backup_base
    )

    env_backup_model = (
        os.environ.get("MOONSHOT_MODEL_BACKUP")
        or os.environ.get("DEEPSEEK_MODEL_BACKUP")
        or os.environ.get("BACKUP_LLM_MODEL")
    )
    if env_backup_model:
        backup_model = env_backup_model
    elif hardcoded_backup_model:
        backup_model = hardcoded_backup_model
    elif "moonshot.cn" in str(backup_api_base or ""):
        backup_model = default_moonshot_model
    else:
        backup_model = default_public_model

    internal_template_url = (
        os.environ.get("DEEPSEEK_INTERNAL_TEMPLATE_URL")
        or default_internal_template_url
    )

    verify_ssl = _resolve_bool_env("VERIFY_SSL", False)
    default_temperature = float(os.environ.get("DEEPSEEK_DEFAULT_TEMPERATURE", "0.7") or 0.7)
    default_max_tokens = int(os.environ.get("DEEPSEEK_DEFAULT_MAX_TOKENS", "2000") or 2000)
    default_stream = _resolve_bool_env("DEEPSEEK_DEFAULT_STREAM", True)

    return LLMProviderConfig(
        access_code=str(access_code or "").strip(),
        primary_api_key=str(primary_api_key or "").strip(),
        primary_api_base=str(primary_api_base or "").strip(),
        primary_model=str(primary_model or "").strip(),
        backup_api_key=str(backup_api_key or "").strip(),
        backup_api_base=str(backup_api_base or "").strip(),
        backup_model=str(backup_model or "").strip(),
        internal_template_url=str(internal_template_url or "").strip(),
        verify_ssl=verify_ssl,
        default_temperature=default_temperature,
        default_max_tokens=default_max_tokens,
        default_stream=default_stream,
    )


def load_dify_workflow_config(
    *,
    default_api_base: str,
    default_api_key: str,
    default_query_key: str,
    default_context_key: str,
    default_user_prefix: str,
    override_api_base: Optional[str] = None,
    override_api_key: Optional[str] = None,
) -> DifyWorkflowConfig:
    load_workspace_env()

    api_base = str(override_api_base or os.environ.get("DIFY_API_BASE") or default_api_base or "").strip().rstrip("/")
    api_key = str(override_api_key or os.environ.get("DIFY_API_KEY") or default_api_key or "").strip()
    query_key = str(os.environ.get("DIFY_WORKFLOW_QUERY_KEY") or default_query_key or "query").strip()
    context_key = str(os.environ.get("DIFY_WORKFLOW_CONTEXT_KEY") or default_context_key or "context").strip()
    user_prefix = str(os.environ.get("DIFY_USER_PREFIX") or default_user_prefix or "preanalysis").strip()
    timeout = float(os.environ.get("DIFY_TIMEOUT", "120") or 120)
    response_mode = str(os.environ.get("DIFY_RESPONSE_MODE") or "blocking").strip().lower() or "blocking"

    return DifyWorkflowConfig(
        api_base=api_base,
        api_key=api_key,
        query_key=query_key,
        context_key=context_key,
        user_prefix=user_prefix,
        timeout=timeout,
        response_mode=response_mode,
        enabled=bool(api_base and api_key),
    )


__all__ = [
    "DifyWorkflowConfig",
    "LLMProviderConfig",
    "load_dify_workflow_config",
    "load_llm_provider_config",
    "load_workspace_env",
]