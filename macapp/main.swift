// App de barra de menú: muestra la última revisión y controla el servicio de
// launchd. No revisa el tráfico por su cuenta; el único motor es el proceso
// `serve`. Lee state.json y manda los comandos con `bin/TrafficNotifier remote`.
import AppKit

let info = Bundle.main.infoDictionary ?? [:]
// scripts/build-app.sh escribe estas rutas en Info.plist.
let repo = URL(fileURLWithPath: info["TNRepo"] as? String ?? FileManager.default.currentDirectoryPath)
let python = info["TNPython"] as? String ?? "/opt/homebrew/bin/python3.13"
let appVersion = info["CFBundleShortVersionString"] as? String ?? "?"
let service = "gui/\(getuid())/com.alexislopez.trafficnotifier"
let logFile = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/TrafficNotifier.log")

struct State {
    var paused = false
    var report: [String: String]?
}

func readState() -> State {
    guard let data = try? Data(contentsOf: repo.appendingPathComponent("state.json")),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return State() }
    return State(paused: json["paused_at"] is String, report: json["last_report"] as? [String: String])
}

@discardableResult
func run(_ executable: String, _ arguments: [String]) -> (ok: Bool, output: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.environment = ProcessInfo.processInfo.environment.merging(["PYTHON": python]) { $1 }
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    do { try process.run() } catch { return (false, error.localizedDescription) }
    let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    process.waitUntilExit()
    return (process.terminationStatus == 0, output.trimmingCharacters(in: .whitespacesAndNewlines))
}

func notifier(_ arguments: String...) -> (ok: Bool, output: String) {
    run(repo.appendingPathComponent("bin/TrafficNotifier").path, arguments)
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()

    func applicationDidFinishLaunching(_ notification: Notification) {
        menu.delegate = self
        item.menu = menu
        refreshTitle()
        Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { _ in self.refreshTitle() }
    }

    func refreshTitle() {
        let state = readState()
        item.button?.title = state.paused ? "⏸" : (state.report?["icon"] ?? "🚗")
    }

    // El menú se arma cada vez que se abre, con el estado del momento.
    func menuNeedsUpdate(_ menu: NSMenu) {
        refreshTitle()
        menu.removeAllItems()
        let state = readState()

        if !run("/bin/launchctl", ["print", service]).ok {
            add("⚠️ El servicio no está corriendo")
        }
        let config = notifier("validate")
        if !config.ok {
            // La salida es "[fecha] ERROR: mensaje".
            add("⚠️ " + (config.output.components(separatedBy: "ERROR: ").last ?? config.output))
        }
        if state.paused {
            add("⏸ Revisiones automáticas en pausa")
        }
        if let report = state.report, let title = report["title"], let message = report["message"] {
            add(title + day(report["at"]))
            for line in message.components(separatedBy: "\n") {
                if line.hasPrefix("– –") { menu.addItem(.separator()) } else { add(line) }
            }
        } else {
            add("Todavía no hay revisiones")
        }

        menu.addItem(.separator())
        add("Revisar ahora", #selector(check))
        if state.paused {
            add("Iniciar revisiones automáticas", #selector(start))
        } else {
            add("Detener hasta mañana", #selector(stop))
        }
        menu.addItem(.separator())
        add("Editar configuración…", #selector(editConfig))
        add("Ver log", #selector(openLog))
        add("Reiniciar servicio", #selector(restart))
        menu.addItem(.separator())
        add("TrafficNotifier \(appVersion)")
        add("Salir", #selector(quit))
    }

    // Sin acción, el texto es informativo (sale atenuado).
    func add(_ title: String, _ action: Selector? = nil) {
        let entry = NSMenuItem(title: title, action: action, keyEquivalent: "")
        entry.target = self
        menu.addItem(entry)
    }

    // " (ayer)" o la fecha si la última revisión no es de hoy.
    func day(_ iso: String?) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        guard let iso, let date = formatter.date(from: iso), !Calendar.current.isDateInToday(date) else { return "" }
        if Calendar.current.isDateInYesterday(date) { return " (ayer)" }
        formatter.dateFormat = "d MMM"
        return " (\(formatter.string(from: date)))"
    }

    func remote(_ action: String) {
        DispatchQueue.global().async {
            let result = notifier("remote", action)
            DispatchQueue.main.async {
                if !result.ok { self.alert("No se pudo mandar el comando", result.output) }
            }
        }
    }

    func alert(_ title: String, _ text: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = text
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    @objc func check() { remote("check") }
    @objc func stop() { remote("stop") }
    @objc func start() { remote("start") }
    @objc func editConfig() { run("/usr/bin/open", ["-t", repo.appendingPathComponent("config.toml").path]) }
    @objc func openLog() { run("/usr/bin/open", ["-a", "Console", logFile.path]) }
    @objc func restart() {
        let result = run("/bin/launchctl", ["kickstart", "-k", service])
        if !result.ok { alert("No se pudo reiniciar el servicio", result.output + "\n\nInstálalo con scripts/install.sh.") }
    }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)  // solo barra de menú, sin ícono en el Dock
app.run()
