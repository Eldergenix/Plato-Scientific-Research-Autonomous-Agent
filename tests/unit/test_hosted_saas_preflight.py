import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "dashboard" / "scripts" / "check_hosted_saas_preflight.py"
WRAPPER = ROOT / "dashboard" / "scripts" / "check-hosted-saas-preflight.sh"
READINESS = ROOT / "dashboard" / "scripts" / "check-production-readiness.sh"
RAILWAY_DOC = ROOT / "dashboard" / "RAILWAY.md"
README = ROOT / "README.md"
ROOT_ENV_EXAMPLE = ROOT / ".env.example"
FRONTEND_ENV_EXAMPLE = ROOT / "dashboard" / "frontend" / ".env.example"


def run_checker(
    values: dict[str, str],
    *,
    hosted_required: bool = True,
    strict: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(CHECKER), "--source", "railway"]
    if hosted_required:
        args.append("--hosted-required")
    if strict:
        args.append("--strict")
    return subprocess.run(
        args,
        input=json.dumps(values),
        text=True,
        capture_output=True,
        check=False,
    )


def run_wrapper(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run_readiness(
    *args: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(READINESS), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def complete_hosted_values() -> dict[str, str]:
    return {
        "NEXT_PUBLIC_PLATO_AUTH_PROVIDER": "clerk",
        "PLATO_AUTH_PROVIDER": "clerk",
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_test_Y2xlcmsuZXhhbXBsZSQ",
        "CLERK_SECRET_KEY": "sk_test_fakeSecretForHostedBoundary",
        "PLATO_BACKEND_PROXY_SECRET": "0123456789abcdef0123456789abcdef",
        "PLATO_PUBLIC_ORIGIN": "https://discovering.app",
        "NEXT_PUBLIC_CLERK_PROXY_URL": "https://discovering.app/__clerk",
        "NEXT_PUBLIC_CLERK_SIGN_IN_URL": "/sign-in",
        "NEXT_PUBLIC_CLERK_SIGN_UP_URL": "/sign-up",
        "NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL": "/",
        "NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL": "/",
        "NEXT_PUBLIC_PLATO_HOSTED_BILLING": "enabled",
        "PLATO_PUBLICATIONS_DATABASE_URL": "postgresql://postgres:secret@db/plato",
        "DATABASE_URL": "postgresql://postgres:secret@db/plato",
        "PLATO_REDIS_URL": "redis://redis.internal:6379",
        "PLATO_USE_FAKEREDIS": "false",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    }


def test_railway_cli_sample_sets_strict_hosted_readiness_variables() -> None:
    doc = RAILWAY_DOC.read_text(encoding="utf-8")

    for name, expected in complete_hosted_values().items():
        if name in {
            "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
            "CLERK_SECRET_KEY",
            "PLATO_BACKEND_PROXY_SECRET",
            "PLATO_PUBLICATIONS_DATABASE_URL",
            "DATABASE_URL",
            "PLATO_REDIS_URL",
            "ANTHROPIC_API_KEY",
        }:
            assert f"{name}=" in doc
        else:
            assert f"'{name}={expected}'" in doc
    assert "--variables-file /path/to/railway-variables.json" in doc
    assert '{"message":"Application not found"}' in doc
    assert "Reconnect the domain to the `plato` service" in doc


def test_env_examples_include_strict_hosted_readiness_contract() -> None:
    root_env = ROOT_ENV_EXAMPLE.read_text(encoding="utf-8")
    frontend_env = FRONTEND_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "check-local-production-gates.sh" in root_env
    assert (
        "check-hosted-saas-preflight.sh --railway --service plato --environment production --hosted-required --strict"
        in root_env
    )
    assert "--variables-file /path/to/railway-variables.json" in README.read_text(
        encoding="utf-8"
    )
    for name in complete_hosted_values():
        assert f"{name}=" in root_env
        if (
            name.startswith("NEXT_PUBLIC_")
            or name.startswith("CLERK_")
            or name.startswith("PLATO_HOSTED_")
            or name
            in {
                "PLATO_AUTH_PROVIDER",
                "PLATO_BACKEND_PROXY_SECRET",
                "PLATO_PUBLIC_ORIGIN",
            }
        ):
            assert f"{name}=" in frontend_env
    assert "PLATO_HOSTED_USAGE_LEDGER_PATH=" in root_env
    assert "PLATO_HOSTED_USAGE_LEDGER_PATH=" in frontend_env
    assert "DATABASE_URL=" in root_env
    assert "PLATO_PUBLICATIONS_DATABASE_URL=" in root_env


def test_hosted_saas_preflight_passes_complete_values_without_echoing_secrets() -> None:
    values = complete_hosted_values()

    result = run_checker(values)

    assert result.returncode == 0
    assert "OK: hosted SaaS/Lab required variables are present." in result.stdout
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert values["PLATO_BACKEND_PROXY_SECRET"] not in result.stdout
    assert values["CLERK_SECRET_KEY"] not in result.stdout
    assert values["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] not in result.stdout


def test_hosted_saas_preflight_uses_clerk_key_when_proxy_secret_missing() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_BACKEND_PROXY_SECRET")

    result = run_checker(values)

    assert result.returncode == 0
    assert "PLATO_BACKEND_PROXY_SECRET: missing" in result.stdout
    assert "OK: hosted SaaS/Lab required variables are present." in result.stdout
    assert "backend proxy secret can be derived" not in result.stdout


def test_hosted_saas_preflight_fails_without_explicit_or_derived_proxy_secret() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_BACKEND_PROXY_SECRET")
    values.pop("CLERK_SECRET_KEY")

    result = run_checker(values)

    assert result.returncode == 1
    assert "PLATO_BACKEND_PROXY_SECRET: missing" in result.stdout
    assert "CLERK_SECRET_KEY: missing" in result.stdout
    assert (
        "PLATO_BACKEND_PROXY_SECRET must be set to at least 32 characters, "
        "or CLERK_SECRET_KEY must be present so the backend proxy secret can be derived"
        in result.stdout
    )


def test_hosted_saas_preflight_requires_durable_publication_database() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_PUBLICATIONS_DATABASE_URL")
    values.pop("DATABASE_URL")

    result = run_checker(values)

    assert result.returncode == 1
    assert "PLATO_PUBLICATIONS_DATABASE_URL: missing" in result.stdout
    assert "DATABASE_URL: missing" in result.stdout
    assert (
        "PLATO_PUBLICATIONS_DATABASE_URL or DATABASE_URL must be set for durable hosted publications"
        in result.stdout
    )


def test_hosted_saas_preflight_requires_at_least_one_llm_provider_key() -> None:
    values = complete_hosted_values()
    values.pop("ANTHROPIC_API_KEY")

    result = run_checker(values)

    assert result.returncode == 1
    assert "ANTHROPIC_API_KEY: missing" in result.stdout
    assert "OPENAI_API_KEY: missing" in result.stdout
    assert "GOOGLE_API_KEY: missing" in result.stdout
    assert "PERPLEXITY_API_KEY: missing" in result.stdout
    assert "At least one LLM provider key must be set" in result.stdout


def test_hosted_saas_preflight_warns_on_single_container_redis_posture() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_REDIS_URL")
    values["PLATO_USE_FAKEREDIS"] = "true"

    result = run_checker(values)

    assert result.returncode == 0
    assert "Warnings:" in result.stdout
    assert "PLATO_REDIS_URL is not set" in result.stdout
    assert "PLATO_USE_FAKEREDIS should be false" in result.stdout


def test_hosted_saas_preflight_allows_warnings_without_strict_mode() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_PUBLIC_ORIGIN")

    result = run_checker(values)

    assert result.returncode == 0
    assert "Warnings:" in result.stdout
    assert (
        "PLATO_PUBLIC_ORIGIN should be the canonical HTTPS app origin" in result.stdout
    )
    assert "OK: hosted SaaS/Lab required variables are present." in result.stdout


def test_hosted_saas_preflight_strict_fails_on_warnings() -> None:
    values = complete_hosted_values()
    values.pop("PLATO_PUBLIC_ORIGIN")

    result = run_checker(values, strict=True)

    assert result.returncode == 1
    assert "Warnings:" in result.stdout
    assert "Errors:" in result.stdout
    assert "hosted preflight emitted warnings" in result.stdout


def test_hosted_saas_preflight_matches_runtime_publishable_key_validation() -> None:
    values = complete_hosted_values()
    values["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] = "pk_test_bm90LWEtY2xlcmstaG9zdA"

    result = run_checker(values)

    assert result.returncode == 1
    assert "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: set" in result.stdout
    assert "does not look like a Clerk publishable key" in result.stdout
    assert values["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] not in result.stdout


def test_hosted_saas_preflight_rejects_bad_public_origin_and_proxy_url() -> None:
    values = complete_hosted_values()
    values["PLATO_PUBLIC_ORIGIN"] = "http://discovering.app/app"
    values["NEXT_PUBLIC_CLERK_PROXY_URL"] = "https://other.example/clerk"

    result = run_checker(values)

    assert result.returncode == 1
    assert "PLATO_PUBLIC_ORIGIN must be an HTTPS origin without a path" in result.stdout
    assert (
        "NEXT_PUBLIC_CLERK_PROXY_URL must point to the /__clerk proxy path"
        in result.stdout
    )


def test_hosted_saas_preflight_rejects_proxy_url_on_wrong_host() -> None:
    values = complete_hosted_values()
    values["NEXT_PUBLIC_CLERK_PROXY_URL"] = "https://other.example/__clerk"

    result = run_checker(values)

    assert result.returncode == 1
    assert (
        "NEXT_PUBLIC_CLERK_PROXY_URL must use the PLATO_PUBLIC_ORIGIN host"
        in result.stdout
    )


def test_hosted_saas_preflight_rejects_external_clerk_app_paths() -> None:
    values = complete_hosted_values()
    values["NEXT_PUBLIC_CLERK_SIGN_IN_URL"] = "https://evil.example/sign-in"
    values["NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL"] = "dashboard"

    result = run_checker(values)

    assert result.returncode == 1
    assert (
        "NEXT_PUBLIC_CLERK_SIGN_IN_URL must be a same-origin app path starting with '/'"
        in result.stdout
    )
    assert (
        "NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL must be a same-origin app path starting with '/'"
        in result.stdout
    )


def test_hosted_saas_preflight_skips_when_hosted_mode_not_requested() -> None:
    result = run_checker({}, hosted_required=False)

    assert result.returncode == 0
    assert "Hosted SaaS/Lab preflight: skipped" in result.stdout


def test_wrapper_rejects_service_without_railway() -> None:
    result = run_wrapper("--service", "plato", "--hosted-required")

    assert result.returncode == 2
    assert "--service/--environment require --railway" in result.stderr


def test_wrapper_passes_service_and_environment_to_railway(tmp_path: Path) -> None:
    values_file = tmp_path / "values.json"
    args_file = tmp_path / "railway-args.txt"
    railway = tmp_path / "railway"
    values_file.write_text(json.dumps(complete_hosted_values()), encoding="utf-8")
    railway.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf "%s\\n" "$@" > "$RAILWAY_ARGS_FILE"',
                'cat "$RAILWAY_VALUES_FILE"',
            ]
        ),
        encoding="utf-8",
    )
    railway.chmod(0o755)
    env = {
        "PATH": f"{tmp_path}:{ROOT / 'node_modules' / '.bin'}:/usr/bin:/bin",
        "RAILWAY_ARGS_FILE": str(args_file),
        "RAILWAY_VALUES_FILE": str(values_file),
    }

    result = run_wrapper(
        "--railway",
        "--service",
        "plato",
        "--environment",
        "production",
        "--hosted-required",
        env=env,
    )

    assert result.returncode == 0
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "variables",
        "--json",
        "--service",
        "plato",
        "--environment",
        "production",
    ]
    assert "OK: hosted SaaS/Lab required variables are present." in result.stdout
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert "0123456789abcdef0123456789abcdef" not in result.stdout
    assert "sk_test_fakeSecretForHostedBoundary" not in result.stdout


def write_fake_railway_and_curl(
    tmp_path: Path,
    *,
    build_log: str = "build complete\n",
    deploy_log: str = "runtime ready\n",
    auth_body: str = '{"user_id":null,"auth_required":true}',
    auth_status: int = 200,
    projects_status: int = 401,
    page_body: str = '<html><body data-clerk-publishable-key="pk_test">ok</body></html>',
    page_status: int = 200,
    values: dict[str, str] | None = None,
    railway_variables_exit: int = 0,
    railway_variables_json_exit: int | None = None,
    railway_variables_kv_exit: int | None = None,
    railway_variables_failures_before_success: int = 0,
    curl_failures_before_success: int = 0,
) -> dict[str, str]:
    values_for_fixture = values or complete_hosted_values()
    json_exit = (
        railway_variables_exit
        if railway_variables_json_exit is None
        else railway_variables_json_exit
    )
    kv_exit = (
        railway_variables_exit
        if railway_variables_kv_exit is None
        else railway_variables_kv_exit
    )
    values_file = tmp_path / "values.json"
    values_kv_file = tmp_path / "values.env"
    railway_args_file = tmp_path / "railway-args.txt"
    curl_args_file = tmp_path / "curl-args.txt"
    curl_attempts_file = tmp_path / "curl-attempts.txt"
    railway_variables_attempts_file = tmp_path / "railway-variable-attempts.txt"
    build_log_file = tmp_path / "build.log"
    deploy_log_file = tmp_path / "deploy.log"
    railway = tmp_path / "railway"
    curl = tmp_path / "curl"

    values_file.write_text(json.dumps(values_for_fixture), encoding="utf-8")
    values_kv_file.write_text(
        "\n".join(f"{key}={value}" for key, value in values_for_fixture.items()),
        encoding="utf-8",
    )
    build_log_file.write_text(build_log, encoding="utf-8")
    deploy_log_file.write_text(deploy_log, encoding="utf-8")
    railway.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf "%s\\n" "$@" >> "$RAILWAY_ARGS_FILE"',
                'if [ "$1" = "variables" ]; then',
                "  attempts=0",
                '  if [ -f "$RAILWAY_VARIABLE_ATTEMPTS_FILE" ]; then attempts="$(cat "$RAILWAY_VARIABLE_ATTEMPTS_FILE")"; fi',
                "  attempts=$((attempts + 1))",
                '  printf "%s" "$attempts" > "$RAILWAY_VARIABLE_ATTEMPTS_FILE"',
                f"  if [ \"$attempts\" -le '{railway_variables_failures_before_success}' ]; then echo 'Transient fetch failure' >&2; exit 8; fi",
                '  if printf "%s\\n" "$@" | grep -qx -- "--json"; then',
                f"    if [ '{json_exit}' != '0' ]; then echo 'Failed to fetch JSON variables' >&2; exit {json_exit}; fi",
                '    cat "$RAILWAY_VALUES_FILE"',
                '  elif printf "%s\\n" "$@" | grep -qx -- "--kv"; then',
                f"    if [ '{kv_exit}' != '0' ]; then echo 'Failed to fetch KV variables' >&2; exit {kv_exit}; fi",
                '    cat "$RAILWAY_VALUES_KV_FILE"',
                "  else",
                '    echo "unexpected railway variables args: $*" >&2',
                "    exit 9",
                "  fi",
                'elif [ "$1" = "logs" ] && printf "%s\\n" "$@" | grep -qx -- "--build"; then',
                '  cat "$RAILWAY_BUILD_LOG_FILE"',
                'elif [ "$1" = "logs" ] && printf "%s\\n" "$@" | grep -qx -- "--deployment"; then',
                '  cat "$RAILWAY_DEPLOY_LOG_FILE"',
                "else",
                '  echo "unexpected railway args: $*" >&2',
                "  exit 9",
                "fi",
            ]
        ),
        encoding="utf-8",
    )
    curl.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf "%s\\n" "$@" >> "$CURL_ARGS_FILE"',
                'out=""',
                'url="${@: -1}"',
                'while [ "$#" -gt 0 ]; do',
                '  if [ "$1" = "-o" ]; then out="$2"; shift; fi',
                "  shift",
                "done",
                "attempts=0",
                'if [ -f "$CURL_ATTEMPTS_FILE" ]; then attempts="$(cat "$CURL_ATTEMPTS_FILE")"; fi',
                "attempts=$((attempts + 1))",
                'printf "%s" "$attempts" > "$CURL_ATTEMPTS_FILE"',
                f"if [ \"$attempts\" -le '{curl_failures_before_success}' ]; then",
                '  printf \'{"status":"error","code":404,"message":"Application not found"}\' > "$out"',
                "  printf '404'",
                "  exit 0",
                "fi",
                'case "$url" in',
                "  */api/v1/health)",
                '    printf \'{"ok":true,"demo_mode":false}\' > "$out"',
                "    printf '200'",
                "    ;;",
                "  */api/v1/auth/me)",
                f'    printf {auth_body!r} > "$out"',
                f"    printf '{auth_status}'",
                "    ;;",
                "  */api/v1/projects)",
                '    printf \'{"code":"auth_required"}\' > "$out"',
                f"    printf '{projects_status}'",
                "    ;;",
                "  */login|*/settings/account|*/settings/organization|*/settings/billing)",
                f'    printf {page_body!r} > "$out"',
                f"    printf '{page_status}'",
                "    ;;",
                "  *)",
                '    printf "{}" > "$out"',
                "    printf '404'",
                "    ;;",
                "esac",
            ]
        ),
        encoding="utf-8",
    )
    railway.chmod(0o755)
    curl.chmod(0o755)

    return {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "RAILWAY_VALUES_FILE": str(values_file),
        "RAILWAY_VALUES_KV_FILE": str(values_kv_file),
        "RAILWAY_ARGS_FILE": str(railway_args_file),
        "RAILWAY_VARIABLE_ATTEMPTS_FILE": str(railway_variables_attempts_file),
        "RAILWAY_BUILD_LOG_FILE": str(build_log_file),
        "RAILWAY_DEPLOY_LOG_FILE": str(deploy_log_file),
        "CURL_ARGS_FILE": str(curl_args_file),
        "CURL_ATTEMPTS_FILE": str(curl_attempts_file),
    }


def test_production_readiness_passes_with_clean_live_checks_and_logs(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path)

    result = run_readiness(
        "--service",
        "plato",
        "--environment",
        "production",
        "--origin",
        "https://discovering.app",
        env=env,
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "build log scan clean" in result.stdout
    assert "deployment log scan clean" in result.stdout
    assert "HTTP 200 https://discovering.app/api/v1/auth/me" in result.stdout
    assert "HTTP 200 https://discovering.app/settings/organization" in result.stdout
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert "Next steps to clear production blockers" not in result.stdout
    assert "0123456789abcdef0123456789abcdef" not in result.stdout
    assert "sk_test_fakeSecretForHostedBoundary" not in result.stdout


def test_production_readiness_fails_on_log_markers(tmp_path: Path) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        build_log="WARNING: Running pip as root\n",
        deploy_log="curl: (7) Failed to connect\n",
    )

    result = run_readiness("--origin", "https://discovering.app", env=env)

    assert result.returncode == 1
    assert "build log scan found warning/error markers" in result.stderr
    assert "deployment log scan found warning/error markers" in result.stderr
    assert "Next steps to clear production blockers" in result.stdout
    assert "Hosted variables look complete in Railway." in result.stdout
    assert (
        "Deploy the current checkout once so local warning fixes reach Railway"
        in result.stdout
    )
    assert "railway up" in result.stdout
    assert "railway variables --service plato" not in result.stdout
    assert "0123456789abcdef0123456789abcdef" not in result.stdout
    assert "Production readiness checks failed." in result.stderr


def test_production_readiness_fails_on_preflight_warnings(tmp_path: Path) -> None:
    values = complete_hosted_values()
    values.pop("PLATO_PUBLIC_ORIGIN")
    env = write_fake_railway_and_curl(tmp_path, values=values)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "Warnings:" in result.stdout
    assert "hosted preflight emitted warnings" in result.stdout
    assert "Next steps to clear production blockers" in result.stdout
    assert (
        "railway variables --service plato --environment production --skip-deploys --set "
        in result.stdout
    )
    assert "PLATO_PUBLIC_ORIGIN=https://discovering.app" in result.stdout
    assert (
        'PLATO_BACKEND_PROXY_SECRET="$(openssl rand -base64 32)"' not in result.stdout
    )
    assert "NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled" not in result.stdout
    assert "Production readiness checks failed." in result.stderr


def test_production_readiness_does_not_guess_variables_when_railway_read_fails(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, railway_variables_exit=7)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "failed to read Railway variables" in result.stderr
    assert "Restore Railway CLI variable access" in result.stdout
    assert "cannot safely infer which hosted variables are missing" in result.stdout
    assert (
        "railway variables --json --service plato --environment production"
        in result.stdout
    )
    assert (
        'PLATO_BACKEND_PROXY_SECRET="$(openssl rand -base64 32)"' not in result.stdout
    )
    assert (
        "railway variables --service plato --environment production --skip-deploys"
        not in result.stdout
    )


def test_production_readiness_retries_transient_railway_variable_read(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        railway_variables_failures_before_success=2,
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "railway variables read failed; retrying (1/3)" in result.stderr
    assert "railway variables read failed; retrying (2/3)" not in result.stderr


def test_production_readiness_falls_back_to_kv_when_json_variables_fail(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        railway_variables_json_exit=7,
        railway_variables_kv_exit=0,
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert "Failed to fetch JSON variables" in result.stderr
    assert "0123456789abcdef0123456789abcdef" not in result.stdout


def test_production_readiness_accepts_local_json_variables_snapshot(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, railway_variables_exit=7)
    variables_file = tmp_path / "manual-variables.json"
    variables_file.write_text(json.dumps(complete_hosted_values()), encoding="utf-8")

    result = run_readiness(
        "--skip-logs",
        "--origin",
        "https://discovering.app",
        "--variables-file",
        str(variables_file),
        env=env,
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "failed to read Railway variables" not in result.stderr
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert "0123456789abcdef0123456789abcdef" not in result.stdout


def test_production_readiness_accepts_local_kv_variables_snapshot(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, railway_variables_exit=7)
    variables_file = tmp_path / "manual-variables.env"
    variables_file.write_text(
        "\n".join(f"{key}={value}" for key, value in complete_hosted_values().items()),
        encoding="utf-8",
    )

    result = run_readiness(
        "--skip-logs",
        "--origin",
        "https://discovering.app",
        "--variables-file",
        str(variables_file),
        env=env,
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "failed to read Railway variables" not in result.stderr
    assert "PLATO_BACKEND_PROXY_SECRET: set (32 chars)" in result.stdout
    assert "0123456789abcdef0123456789abcdef" not in result.stdout


def test_production_readiness_fails_when_local_variables_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path)
    variables_file = tmp_path / "missing.json"

    result = run_readiness(
        "--skip-logs",
        "--origin",
        "https://discovering.app",
        "--variables-file",
        str(variables_file),
        env=env,
    )

    assert result.returncode == 1
    assert f"--variables-file does not exist: {variables_file}" in result.stderr
    assert "Restore Railway CLI variable access" in result.stdout


def test_production_readiness_omits_proxy_remediation_when_clerk_can_derive_it(
    tmp_path: Path,
) -> None:
    values = complete_hosted_values()
    values.pop("PLATO_BACKEND_PROXY_SECRET")
    values.pop("PLATO_PUBLIC_ORIGIN")
    values.pop("NEXT_PUBLIC_PLATO_HOSTED_BILLING")
    env = write_fake_railway_and_curl(tmp_path, values=values)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "Next steps to clear production blockers" in result.stdout
    assert 'PLATO_BACKEND_PROXY_SECRET="$(openssl rand -base64 32)"' not in result.stdout
    assert "PLATO_BACKEND_PROXY_SECRET=${PLATO_BACKEND_PROXY_SECRET}" not in result.stdout
    assert "PLATO_PUBLIC_ORIGIN=https://discovering.app" in result.stdout
    assert "NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled" in result.stdout
    assert (
        "Deploy the current checkout once after those variables are set"
        in result.stdout
    )
    assert "0123456789abcdef0123456789abcdef" not in result.stdout


def test_production_readiness_remediation_does_not_hide_secret_preflight_failures(
    tmp_path: Path,
) -> None:
    values = complete_hosted_values()
    values.pop("CLERK_SECRET_KEY")
    env = write_fake_railway_and_curl(tmp_path, values=values)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert (
        "CLERK_SECRET_KEY is missing or does not look like a Clerk secret key"
        in result.stdout
    )
    assert (
        "Resolve the hosted preflight errors or warnings printed above."
        in result.stdout
    )
    assert "Secret-valued variables such as Clerk keys" in result.stdout
    assert "Hosted variables look complete in Railway." not in result.stdout
    assert "railway variables --service plato" not in result.stdout
    assert "sk_test_fakeSecretForHostedBoundary" not in result.stdout


def test_production_readiness_fails_when_signed_out_auth_status_is_not_required(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        auth_body='{"user_id":"stale-local-user","auth_required":false}',
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 200 https://discovering.app/api/v1/auth/me" in result.stdout
    assert (
        "expected signed-out /api/v1/auth/me to report auth_required=true and user_id=null"
        in result.stderr
    )


def test_production_readiness_retries_transient_application_not_found_routes(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, curl_failures_before_success=2)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 0
    assert "OK: production readiness checks passed." in result.stdout
    assert "/api/v1/health returned HTTP 404; retrying (1/3)" in result.stderr
    assert "/api/v1/health returned HTTP 404; retrying (2/3)" in result.stderr
    assert "HTTP 200 https://discovering.app/api/v1/health" in result.stdout


def test_production_readiness_reports_stable_application_not_found_routes(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, curl_failures_before_success=99)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 404 https://discovering.app/api/v1/health" in result.stdout
    assert "health check failed" in result.stderr
    assert (
        "Restore the public domain routing/deployment for https://discovering.app"
        in result.stdout
    )
    assert "Reconnect the domain to the plato service" in result.stdout
    assert (
        "Routes that ended in Railway Application not found after retries:"
        in result.stdout
    )
    assert "       - /api/v1/health" in result.stdout
    assert "       - /settings/billing" in result.stdout
    assert "railway up" in result.stdout


def test_production_readiness_fails_when_projects_boundary_is_public(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(tmp_path, projects_status=200)

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 200 https://discovering.app/api/v1/projects" in result.stdout
    assert "expected unauthenticated /api/v1/projects to return 401" in result.stderr


def test_production_readiness_fails_when_hosted_pages_render_errors(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        page_body="<html><body>Application error</body></html>",
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 200 https://discovering.app/settings/account" in result.stdout
    assert "/settings/account rendered an app-error marker" in result.stderr
    assert "Production readiness checks failed." in result.stderr


def test_production_readiness_fails_when_hosted_pages_render_saas_fallbacks(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        page_body='<html><body data-clerk-publishable-key="pk_test"><section data-testid="billing-auth-config-error">hosted config error</section></body></html>',
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 200 https://discovering.app/settings/billing" in result.stdout
    assert (
        "/settings/billing rendered a hosted SaaS/Lab fallback or warning marker"
        in result.stderr
    )
    assert "Production readiness checks failed." in result.stderr


def test_production_readiness_fails_when_hosted_page_marker_is_missing(
    tmp_path: Path,
) -> None:
    env = write_fake_railway_and_curl(
        tmp_path,
        page_body="<html><body>self-hosted fallback</body></html>",
    )

    result = run_readiness(
        "--skip-logs", "--origin", "https://discovering.app", env=env
    )

    assert result.returncode == 1
    assert "HTTP 200 https://discovering.app/login" in result.stdout
    assert "/login did not render expected hosted marker" in result.stderr
    assert "data-clerk-publishable-key" in result.stderr
