# 04 Release-Workflow (Git)

## 1 Branching
- Trunk-basiert: `main` ist immer releasefähig und geschützt (PR-Pflicht, grüne Checks, linearer Verlauf).
- Kurzlebige Branches: `feat/<thema>`, `fix/<thema>`, `docs/<thema>`, `chore/<thema>`. Squash-Merge.
- Keine langlebigen Release-Branches; Hotfix = normaler `fix:`-PR + Patch-Release.

## 2 Commits und Versionierung
- Conventional Commits; `feat:` → Minor, `fix:`/`perf:` → Patch, `feat!:`/`BREAKING CHANGE:` → Major.
- Semantic Versioning. Version steht in `manifest.json` (`version`) – wird vom Release-Prozess gesetzt.
- Commit-Messages und PR-Titel auf Englisch; PR-Beschreibung verweist auf AK-n der Spezifikation.

## 3 Release-Ablauf (semantic-release)
1. Merge nach `main` → Workflow `release.yml`: Job `test` (ruff, mypy, pytest) ist **Gate**; nur wenn er
   grün ist, läuft Job `release` (`needs: test`).
2. semantic-release wertet die Conventional Commits seit dem letzten Tag aus. Ohne `feat`/`fix`/`perf`/
   `BREAKING CHANGE` entsteht kein Release (`docs`, `chore`, `ci`, `test` lösen nichts aus).
3. Bei einem Release: `scripts/bump_version.py` setzt `version` in `manifest.json`, `netzentgelt_rechner.zip`
   (Inhalt von `custom_components/netzentgelt_rechner/`) wird gebaut, `CHANGELOG.md` erzeugt; CI committet
   `chore(release): x.y.z [skip ci]` (**nie von Hand**), setzt Tag `vX.Y.Z` und hängt das ZIP ans GitHub-Release.
4. `hacs.json` mit `"zip_release": true`, `"filename": "netzentgelt_rechner.zip"` → HACS lädt das ZIP.
- Konfiguration: `.releaserc.json`. Browser-/E2E-Tests laufen im PR (`ci.yml`), sind aber kein Release-Gate.
- Voraussetzung: Branch-Schutz von `main` muss Pushes des Release-Commits durch GitHub Actions erlauben.

## 4 CI-Jobs (`.github/workflows/ci.yml`)
| Job | Inhalt |
|---|---|
| lint | ruff check, ruff format --check, mypy |
| test | pytest Unit + Integration, Coverage-Gate (calc ≥ 95 % Zweige) |
| hassfest | `home-assistant/actions/hassfest` |
| hacs | `hacs/action` (category: integration) |
| e2e | Matrix HA 2026.2.x / 2026.10.x, `scripts/e2e.sh` (HA-Log als Artefakt) |
| ui | Visuelle Tests im echten Frontend (Playwright), `scripts/e2e-ui.sh`, Screenshots als Artefakt `ui-screenshots`; kein Release-Gate |

## 5 Definition of Release
- Alle Gates grün auf dem Release-Commit.
- CHANGELOG automatisch (semantic-release); Spezifikationen konsistent mit dem Verhalten (Reviewpunkt im PR-Template).
- Installationshinweis in README (HACS Custom Repository oder manuelles Kopieren).
- Rollback = vorheriges Release in HACS neu installieren; Datenmodell-Migrationen sind abwärts tolerant
  (Store-Version, siehe Tech-Spec §3.4).

## 6 Repository-Einstellungen (einmalig)
Branch-Schutz `main`, Squash-Merge only, Secrets nicht nötig (keine Veröffentlichung außerhalb GitHub),
Dependabot für Actions und Python-Entwicklungsabhängigkeiten.
