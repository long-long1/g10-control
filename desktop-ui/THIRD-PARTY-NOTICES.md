# Third-party notices

This notice is for the G10 Control desktop shell and its current development dependencies. The frozen Windows package in a later release must include the corresponding upstream license texts for every bundled direct and transitive dependency.

- **pywebview 6.2.1** — BSD 3-Clause. Copyright (c) 2014–2017 Roman Sirokov. Its license text is available from the [pywebview project](https://github.com/r0x0r/pywebview) and is recorded in the installed package metadata.
- **pythonnet 3.2.1** — MIT. [pythonnet project](https://github.com/pythonnet/pythonnet).
- **pystray 0.19.5** — GNU LGPL v3. The upstream `COPYING` and `COPYING.LGPL` texts are included in [`licenses`](licenses).
- **React 18.3.1**, **React DOM 18.3.1**, **Vite 6.4.4**, **TypeScript 5.9.3**, **@vitejs/plugin-react 4.7.0**, and **lucide-react 0.468.0** — MIT. The exact versions are pinned in `web/package-lock.json`; the package license files are present in `web/node_modules` during development.
- **AxonKey** — used only as a behavior and feature reference. No AxonKey source code, artwork, or UI assets are included. The inspected reference checkout at commit `a8c23b98fc6468013c9647a8b27646e5a9821303` had no root `LICENSE` file, so source reuse is deferred pending a clear license grant.

Before distributing a Windows installer, regenerate a complete license report from the locked Python and npm dependency sets and ship every required notice and license text. The current working tree is not yet an installer-ready software bill of materials.

For the local v0.1.0 Beta candidate, `build/stage_beta.py` collects installed Python/npm notices and the Python license stack into `licenses/` and records the scope, versions and missing texts in `license-inventory.json`. See `docs/BETA_LICENSE_REVIEW.md` in source (`BETA-LICENSE-REVIEW.md` in the candidate) for unresolved overall-project authorization, LGPL source/replacement obligations and native SDK/license gaps. This collection does not authorize external distribution; no ZIP or Release is produced.
