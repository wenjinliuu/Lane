# Lane agent instructions

Before changing this repository, read `docs/maintenance.md`. Treat `config/*.yaml`, the generator,
validator, tests, and checked-in `dist/` artifacts as one atomic system.

## Required workflow

1. Change the declarative source or generator; do not patch generated behavior only in `dist/`.
2. Update validation and regression tests for every behavior change.
3. Regenerate all affected client profiles and rule artifacts.
4. Run `python -m pytest`, `lane check`, and `git diff --check` before committing.
5. Keep the root README short and user-facing. Put implementation rationale in
   `docs/maintenance.md`; keep incident timelines in separate historical documents.

## Hard constraints

- Preserve six-client routing semantics while using client-native syntax.
- Preserve the routing order and client-specific policy-group behavior documented in
  `docs/maintenance.md`.
- Never add private subscription URLs, credentials, sample live nodes, MitM hosts, certificates,
  remote scripts, or rewrites to generated profiles.
- QX must use `代理选择`, must not define a custom `Proxy` or redundant `我的节点`, and must keep
  app-managed node resources plus the complete empty-section skeleton.
- Shadowrocket uses built-in `PROXY`; Surge uses Smart region groups; Stash specialized providers
  and Egern single-load/flatten behavior must remain intact.
- Keep third-party provenance and license notices when changing upstream data or icons.
- Do not bypass the CN-IP change breaker without the exact reviewed candidate SHA-256.
