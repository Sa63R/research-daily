import Darwin
import Foundation

private let runnerName = "GreenDailyRunner"
private let runnerIdentifier = "com.jielosc.greendaily.runner"

private func writeStandardError(_ message: String) {
    let data = Data((message + "\n").utf8)
    FileHandle.standardError.write(data)
}

private func fail(_ message: String, status: Int32 = 1) -> Never {
    writeStandardError("\(runnerName): \(message)")
    exit(status)
}

private func requireExecutable(_ url: URL, label: String) {
    guard FileManager.default.isExecutableFile(atPath: url.path) else {
        fail("\(label) is missing or not executable: \(url.path)")
    }
}

private let requestedMode: String = {
    let arguments = Array(CommandLine.arguments.dropFirst())
    if arguments.isEmpty {
        return "run"
    }
    if arguments == ["--check"] {
        return "check"
    }
    fail("unsupported arguments; only --check is accepted", status: 2)
}()

let bundleURL = Bundle.main.bundleURL.standardizedFileURL
guard bundleURL.pathExtension == "app" else {
    fail("must run from the GreenDailyRunner.app bundle")
}
guard Bundle.main.bundleIdentifier == runnerIdentifier else {
    fail("unexpected bundle identifier: \(Bundle.main.bundleIdentifier ?? "missing")")
}

// The stable app lives at <repo>/.runner/GreenDailyRunner.app. Keeping the
// repository relationship fixed avoids accepting an arbitrary script path.
let repoRoot = bundleURL
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .resolvingSymlinksInPath()
let pipelineScript = repoRoot
    .appendingPathComponent("scripts/daily_pipeline.sh")
    .resolvingSymlinksInPath()
let pythonCommand = repoRoot
    .appendingPathComponent(".venv/bin/python")
    .standardizedFileURL

requireExecutable(pipelineScript, label: "daily pipeline")
requireExecutable(pythonCommand, label: "project Python")

if requestedMode == "check" {
    print("runner_identifier=\(runnerIdentifier)")
    print("runner_bundle=\(bundleURL.path)")
    print("repo_root=\(repoRoot.path)")
    print("pipeline=\(pipelineScript.path)")
    print("python=\(pythonCommand.path)")
    exit(0)
}

var environment = ProcessInfo.processInfo.environment
for key in ["BASH_ENV", "ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"] {
    environment.removeValue(forKey: key)
}
for key in Array(environment.keys) where key.hasPrefix("DYLD_") {
    environment.removeValue(forKey: key)
}
environment["GREEN_DAILY_RUNNER"] = runnerIdentifier

let child = Process()
child.executableURL = URL(fileURLWithPath: "/bin/bash")
child.arguments = [
    pipelineScript.path,
    "--repo-root", repoRoot.path,
    "--python-command", pythonCommand.path,
]
child.currentDirectoryURL = repoRoot
child.environment = environment

signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let signalQueue = DispatchQueue(label: "com.jielosc.greendaily.runner.signals")
let interruptSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: signalQueue)
let terminateSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: signalQueue)
for source in [interruptSource, terminateSource] {
    source.setEventHandler {
        if child.isRunning {
            child.terminate()
        }
    }
    source.resume()
}

do {
    try child.run()
} catch {
    fail("failed to start the daily pipeline: \(error)")
}

child.waitUntilExit()
interruptSource.cancel()
terminateSource.cancel()
exit(child.terminationStatus)
