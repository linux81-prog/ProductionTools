# Network Security and Privacy: What Protects What

ProductionTools is built to work fully offline. It's important to be clear about
**which protections come from the app itself** and **which are enforced
independently by your Mac or other software**. They are not the same thing.

## 1. Safeguards inside the app (application level)

| Safeguard | What it does | Its limits |
|---|---|---|
| **Network lock** (`core/netguard.py`) | When ProductionTools starts, it refuses every attempt by its own code to connect to anything except this computer (127.0.0.1). It also refuses outside DNS lookups (a computer asking the internet for a website's address). Every attempt is recorded. | It only covers the ProductionTools Python process. It cannot see or stop other programs (Excel, your browser, LibreOffice). Native code that bypasses Python's networking would not be caught. |
| **Local-only web server** (Stage 3) | The app's page is served only at `127.0.0.1`, so other devices on your network can't reach it. | It's a setting in the app, not a firewall rule. |
| **Browser lock** (Stage 3/5) | Every page tells your browser to load nothing from the internet (a "Content-Security-Policy" setting). All fonts and scripts are bundled with the app. | Your browser enforces it, but only for ProductionTools pages. |
| **Bundled OCR models** | The text-reading engine's models ship inside the app, so nothing is downloaded while it runs. | — |
| **Automated tests** | The whole test suite runs with the network lock on. A hidden internet dependency would make the tests fail. | This proves the app's own code works offline. It's not a guarantee about the Mac as a whole. |

These are good engineering practice, but **they are not operating-system enforcement.**

## 2. macOS's built-in firewall: incoming connections only

The firewall in **System Settings → Network → Firewall** filters **incoming**
connections, meaning other computers trying to reach yours. **It does not stop any
app, ProductionTools or Excel included, from sending data out.** Turning it on is
sensible, but it is not proof that nothing leaves your Mac.

## 3. Outbound restrictions enforced independently of the app

These work regardless of ProductionTools' own code:

- **Airplane test (simplest):** turn off Wi-Fi and unplug Ethernet, then process a whole
  envelope, including the Excel export. If everything works, nothing needed the internet.
- **Outbound firewall:** *LuLu* (free, open source, from Objective-See) or *Little Snitch*
  (paid). Each shows a prompt whenever any program, including Excel, tries to connect
  out, and lets you block it permanently.
- **Watching connections:** while the app is running, this Terminal command lists its
  open network connections. It should show only `127.0.0.1` (localhost):

  ```bash
  lsof -i -P | grep -i python
  ```

## 4. Automating Excel (Stage 2, not yet built)

The Excel step would use the macOS **Automation** permission ("ProductionTools wants
to control Microsoft Excel"). That permission covers controlling Excel only and can
be withdrawn at any time in **System Settings → Privacy & Security → Automation**.
Excel is a separate program, so the app's network lock does not cover it. Whether
Excel's PDF export works offline will be proved with the airplane test.

## 5. Your data
- Your real production data stays in a folder on your Mac. It never goes into the code
  repository and is never sent to the developer (the repository's `.gitignore` excludes
  data folders).
- Recommended: turn on **FileVault** (disk encryption) and keep **Time Machine** backups.
