# 04 Release-Workflow (Git)

## 1 Branching
- Trunk-basiert: `main` ist immer releasefähig und geschützt (PR-Pflicht, grüne Checks, linearer Verlauf).
- Kurzlebige Branches: `feat/<thema>`, `fix/<thema>`, `docs/<thema>`, `chore/<thema>`. Squash-Merge.
- Keine langlebigen Release-Branches; Hotfix = normaler `fix:`-PR + Patch-Release.

## 2 Commits und Versionierung
- Conventional Commits; `feat:` → Minor, `fix:`/`perf:` → Patch, `feat!:`/`BREAKING CHANGE:` → Major.
- Semantic Versioning. Version steht in `manifest.json` (`version`) – wird vom Release-Prozess gesetzt.
- Commit-Messages und PR-Titel auf Englisch; PR-Beschreibung verweist auf AK-n der Spezifikation.

## 3 Release-Ablauf (release-please)
1. Merges nach `main` → Action `release-please` pflegt einen Release-PR („chore(main): release x.y.z“)
   mit CHANGELOG.md und Versionssprung in `manifest.json`.
2. Release-PR mergen → Tag `vX.Y.Z` und GitHub-Release werden erzeugt.
3. Job `asset` in `release.yml` (läuft nach release-please, wenn `release_created`; ein Trigger auf `release: published` greift bei `GITHUB_TOKEN`-Releases nicht) baut `netzentgelt_rechner.zip`
   (Inhalt von `custom_components/netzentgelt_rechner/`), hängt es ans Release an.
4. `hacs.json` mit `"zip_release": true`, `"filename": "netzentgelt_rechner.zip"` → HACS lädt das ZIP.
- Vorabversionen: Tag `vX.Y.Z-rc.N` → als Pre-Release markiert, nur E2E-Gate.

## 4 CI-Jobs (`.github/workflows/ci.yml`)
| Job | Inhalt |
|---|---|
| lint | ruff check, ruff format --check, mypy |
| test | pytest Unit + Integration, Coverage-Gate (calc ≥ 95 % Zweige) |
| hassfest | `home-assistant/actions/hassfest` |
| hacs | `hacs/action` (category: integration) |
| e2e | Matrix HA 2026.2.x / 2026.10.x, `scripts/e2e.sh` |

## 5 Definition of Release
- Alle Gates grün auf dem Release-Commit.
- CHANGELOG automatisch; Spezifikationen konsistent mit dem Verhalten (Reviewpunkt im PR-Template).
- Installationshinweis in README (HACS Custom Repository oder manuelles Kopieren).
- Rollback = vorheriges Release in HACS neu installieren; Datenmodell-Migrationen sind abwärts tolerant
  (Store-Version, siehe Tech-Spec §3.4).

## 6 Repository-Einstellungen (einmalig)
Branch-Schutz `main`, Squash-Merge only, Secrets nicht nötig (keine Veröffentlichung außerhalb GitHub),
Dependabot für Actions und Python-Entwicklungsabhängigkeiten.
