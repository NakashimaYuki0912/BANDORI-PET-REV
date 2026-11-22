---
name: bandori-release
description: >-
  Use this skill when preparing a new BandoriPet release, bumping version numbers, 
  building distributables, or performing pre-release validation. Covers version bump, 
  changelog generation, cx_Freeze build, and release artifact preparation.
---

# BandoriPet Release Procedure

## Pre-Release Checklist

Before starting a release, verify all items:

- [ ] All target features merged and working
- [ ] No critical bugs in `bandori_error.log`
- [ ] Tests passing: `python -m pytest tests/`
- [ ] Manual smoke test: launch `python main.py`, verify Live2D + chat works

## Step 1: Version Bump

Edit [app_info.py](../../app_info.py):

```python
APP_VERSION = "X.Y.Z.W"  # e.g., "3.1.0.3"
```

Version format: `MAJOR.MINOR.PATCH.BUILD`
- **MAJOR**: Breaking architecture changes
- **MINOR**: New features
- **PATCH**: Bug fixes
- **BUILD**: Hotfix / incremental builds

## Step 2: Create Release Notes

Create `RELEASE_NOTES_vX.Y.Z.W.md` at project root following existing patterns:
- See [RELEASE_NOTES_v3.1.0.2.md](../../RELEASE_NOTES_v3.1.0.2.md) for reference

Structure:
```markdown
# BandoriPet vX.Y.Z.W Release Notes

## ✨ New Features
- Feature description

## 🐛 Bug Fixes
- Fix description

## 🔧 Improvements
- Improvement description

## ⚠️ Breaking Changes
- (if any)
```

## Step 3: Build Distributables

### cx_Freeze Build (Portable ZIP + MSI)

```bash
python setup.py build
```

This produces the build output in `BUILD/`. Then package:

**Portable ZIP**:
```powershell
Compress-Archive -Path "BUILD\exe.win-amd64-3.10\*" -DestinationPath "BandoriPet-X.Y.Z.W-WIN-AMD64.zip"
```

**MSI Installer**:
```bash
python setup.py bdist_msi
```

Output naming convention:
- `BandoriPet-X.Y.Z.W-WIN-AMD64.zip` (portable)
- `BandoriPet-X.Y.Z.W-win64.msi` (installer)

## Step 4: Validate Build Artifacts

```powershell
# Check ZIP contents
Expand-Archive -Path "BandoriPet-X.Y.Z.W-WIN-AMD64.zip" -DestinationPath "BUILD\verify" -Force
Test-Path "BUILD\verify\BandoriPet.exe"

# Verify version in built exe (if possible)
# Launch and check About dialog
```

## Step 5: Git Tag & Push

```bash
git add -A
git commit -m "@ vX.Y.Z.W: brief description of changes"
git tag vX.Y.Z.W
git push origin main --tags
```

Commit message convention: `@ vX.Y.Z.W: comma-separated change summary`
(See git history for examples)

## Step 6: GitHub Release

Upload to GitHub Releases on `izasaraba/BANDORI-PET-REV`:

1. Create release for tag `vX.Y.Z.W`
2. Paste release notes content
3. Attach artifacts:
   - `BandoriPet-X.Y.Z.W-WIN-AMD64.zip`
   - `BandoriPet-X.Y.Z.W-win64.msi`

## Update Channels

BandoriPet supports three update paths (managed by `app_update.py`):

| Channel | Mechanism | Target Users |
|---------|-----------|-------------|
| **Git** | `git pull --ff-only` | Developers |
| **Portable** | ZIP overlay update | Portable users |
| **MSI** | Installer upgrade | Standard users |

## Post-Release

- [ ] Verify auto-update detects new version
- [ ] Check GitHub Release page renders correctly
- [ ] Announce in QQ group if significant update

## Troubleshooting

| Issue | Solution |
|-------|---------|
| cx_Freeze missing module | Add to `packages` list in `setup.py` |
| MSI build fails | Check `bdist_msi` options in `setup.py` |
| Version not showing | Verify `app_info.py` was saved with UTF-8 |
| Large build size | Check `excludes` list in `setup.py` |
