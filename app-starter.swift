// Safari Assistant — natives Startprogramm der App (Contents/MacOS/<CFBundleExecutable>), 2026-11-15-4
//
// Warum: Bis 2026-11-15 war die Programmdatei der App das Shell-Skript launcher_new.sh. Ein Skript kann auf
// Ereignisse des Docks nicht antworten — ein Klick auf das Dock-Symbol der laufenden App tat nichts, und
// „Beenden“ im Dock ging ins Leere. Dieses kleine Programm startet das unveränderte Startskript
// (Contents/MacOS/launcher.sh) und übernimmt nur, was ein Skript nicht kann:
//   • Klick aufs Dock-Symbol → das offene Fenster der App in Safari nach vorn holen (sonst die Adresse öffnen)
//   • „Beenden“ im Dock → das Startskript beenden; es stoppt Server und (falls selbst gestartet) Ollama
//   • Ende des Startskripts (Server beendet, z. B. über den Ausschalter in der App) → App beendet sich
// deploy.sh übersetzt diese Datei mit swiftc. Geht das nicht, bleibt das Skript die Programmdatei (wie bisher).
import AppKit

final class Starter: NSObject, NSApplicationDelegate {
    private var skript: Process?
    private var beendetSich = false

    private var adressDatei: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Safari Assistant/app-adresse")
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let pfad = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/launcher.sh").path
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [pfad]
        var umgebung = ProcessInfo.processInfo.environment
        umgebung["SAFARI_STARTER_PID"] = String(getpid())   // das Skript beendet sich, wenn dieses Programm verschwindet
        p.environment = umgebung
        do {
            try p.run()
            skript = p
            // Ende des Skripts per Zeitgeber prüfen (Ziel/Selektor statt Closure: bleibt auf dem Haupt-Thread)
            Timer.scheduledTimer(timeInterval: 1.0, target: self, selector: #selector(pruefeSkript),
                                 userInfo: nil, repeats: true)
        } catch {
            let hinweis = NSAlert()
            hinweis.messageText = "Safari Assistant startet nicht"
            hinweis.informativeText = "launcher.sh fehlt im App-Bundle (\(error.localizedDescription)). Im Projektordner ./deploy.sh ausführen."
            hinweis.alertStyle = .critical
            hinweis.runModal()
            beendetSich = true
            NSApp.terminate(nil)
        }
    }

    @objc private func pruefeSkript() {
        guard let p = skript, !p.isRunning, !beendetSich else { return }
        beendetSich = true
        NSApp.terminate(nil)
    }

    // Klick aufs Dock-Symbol, während die App läuft
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        zeigeApp()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        beendetSich = true
        guard let p = skript, p.isRunning else { return }
        p.terminate()                                   // SIGTERM → trap im Skript stoppt Server und Ollama
        let frist = Date().addingTimeInterval(3)
        while p.isRunning && Date() < frist { usleep(50_000) }
    }

    /// Die Adresse, die das Startskript geöffnet hat — nur http://localhost:<port>/… oder http://127.0.0.1:<port>/…
    private func appAdresse() -> URL? {
        guard let text = try? String(contentsOf: adressDatei, encoding: .utf8) else { return nil }
        let roh = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard roh.range(of: "^http://(localhost|127\\.0\\.0\\.1):[0-9]{2,5}/[A-Za-z0-9._/-]*$",
                        options: .regularExpression) != nil else { return nil }
        return URL(string: roh)
    }

    private func zeigeApp() {
        guard let adresse = appAdresse(), let host = adresse.host, let port = adresse.port else { return }
        let browser = NSWorkspace.shared.urlForApplication(toOpen: adresse).flatMap { Bundle(url: $0)?.bundleIdentifier }
        let safariLaeuft = !NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Safari").isEmpty
        if browser == "com.apple.Safari" && safariLaeuft && holeSafariTab(praefix: "http://\(host):\(port)/") {
            return
        }
        NSWorkspace.shared.open(adresse)                // kein offener Tab (oder anderer Browser): Adresse öffnen
    }

    /// Sucht in Safari den Tab der App und holt ihn nach vorn. Beim ersten Mal fragt macOS, ob die App Safari
    /// steuern darf; ohne Erlaubnis (oder ohne Treffer) → false, dann öffnet zeigeApp() die Adresse.
    private func holeSafariTab(praefix: String) -> Bool {
        let quelle = """
        tell application "Safari"
          repeat with w in windows
            try
              repeat with t in tabs of w
                if (URL of t as text) starts with "\(praefix)" then
                  set current tab of w to t
                  set index of w to 1
                  activate
                  return "ja"
                end if
              end repeat
            end try
          end repeat
        end tell
        return "nein"
        """
        var fehler: NSDictionary?
        let ergebnis = NSAppleScript(source: quelle)?.executeAndReturnError(&fehler)
        return fehler == nil && ergebnis?.stringValue == "ja"
    }
}

let app = NSApplication.shared
let starter = Starter()
app.delegate = starter
app.setActivationPolicy(.regular)
app.run()
