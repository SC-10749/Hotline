package cn.hotline.infrastructure.launch;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import cn.hotline.infrastructure.config.PythonLaunchProperties;
import cn.hotline.infrastructure.config.PythonServiceProperties;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Starts the Python gateway and execution worker as local sidecars when the Java process
 * expects Python on the same machine. Skipped when Python is already reachable, when the
 * upstream is remote, or when service discovery owns the Python instances.
 */
@Component
public class PythonProcessLauncher {
    private static final Logger log = LoggerFactory.getLogger(PythonProcessLauncher.class);
    private static final List<String> LOOPBACK_HOSTS = List.of("127.0.0.1", "localhost", "0.0.0.0");
    private static final List<String> VENV_EXECUTABLES =
            List.of(".venv/Scripts/python.exe", ".venv/bin/python", ".venv/Scripts/python", ".venv/bin/python3");

    private final PythonLaunchProperties launch;
    private final PythonServiceProperties python;
    private final List<Process> spawned = new CopyOnWriteArrayList<>();

    public PythonProcessLauncher(PythonLaunchProperties launch, PythonServiceProperties python) {
        this.launch = launch;
        this.python = python;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        if (!launch.enabled()) {
            log.info("Python 自动拉起已关闭，跳过。");
            return;
        }
        if (python.mode() != PythonServiceProperties.Mode.STATIC) {
            log.info("Python 由服务发现接入，跳过本地自动拉起。");
            return;
        }
        String host = python.baseUrl().getHost();
        int port = python.baseUrl().getPort();
        if (host == null || port <= 0 || !LOOPBACK_HOSTS.contains(host)) {
            log.info("Python 上游 {} 不是本机地址，跳过自动拉起。", python.baseUrl());
            return;
        }
        if (isListening(host, port)) {
            log.info("Python 网关已在 {}:{} 运行，跳过自动拉起。", host, port);
            return;
        }
        Path root = resolveRoot();
        if (root == null) {
            log.warn("未定位到 Hotline 项目根目录，跳过 Python 自动拉起。");
            return;
        }
        String command = resolveCommand(root, launch.executable());
        if (command == null) {
            log.warn("未找到本地 Python 解释器（{}/.venv），跳过自动拉起。", root);
            return;
        }
        log.info("Python 自动拉起：根目录 {}，解释器 {}，目标 {}:{}。", root, command, host, port);
        Thread.ofVirtual().name("hotline-python-launcher").start(() -> start(root, command, host, port));
    }

    private void start(Path root, String command, String host, int port) {
        try {
            Process gateway = spawn(root, command,
                    List.of("-m", "uvicorn", "main:app", "--host", host, "--port", String.valueOf(port)));
            spawned.add(gateway);
            // 执行 Worker 数量可配：队列用 SQLite 抢占式领取，多进程即可并行跑多个运行。
            int workers = Math.max(1, launch.workerInstances());
            for (int index = 0; index < workers; index++) {
                Process worker = spawn(root, command,
                        List.of("-m", "python_backend.modules.execution.worker"));
                spawned.add(worker);
            }
            if (awaitPort(host, port, launch.startupTimeout())) {
                log.info("Python 网关与 {} 个执行 Worker 已就绪（{}:{}）。", workers, host, port);
            } else {
                log.error("Python 网关在 {} 内未就绪，请检查 {} 的依赖与启动日志。", launch.startupTimeout(), root);
            }
        } catch (IOException exception) {
            log.error("启动 Python 服务失败：{}", exception.getMessage());
        }
    }

    private Process spawn(Path root, String command, List<String> arguments) throws IOException {
        List<String> line = new ArrayList<>();
        line.add(command);
        line.addAll(arguments);
        Process process = new ProcessBuilder(line)
                .directory(root.toFile())
                .redirectErrorStream(true)
                .inheritIO()
                .start();
        process.onExit().thenAccept(exited -> {
            if (exited.exitValue() != 0) {
                log.error("Python 子进程已退出（代码 {}）：{}", exited.exitValue(), String.join(" ", line));
            }
        });
        return process;
    }

    @PreDestroy
    public void stop() {
        for (Process process : spawned) {
            terminateTree(process);
        }
        if (!spawned.isEmpty()) {
            log.info("已停止由 Java 拉起的 {} 个 Python 进程。", spawned.size());
        }
        spawned.clear();
    }

    /** Kills the process and its children; the virtual environment launcher forks the real interpreter. */
    static void terminateTree(Process process) {
        List<ProcessHandle> descendants = process.descendants().toList();
        descendants.forEach(ProcessHandle::destroy);
        process.destroy();
        try {
            if (!process.waitFor(3, TimeUnit.SECONDS)) {
                process.destroyForcibly();
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
        }
        descendants.stream().filter(ProcessHandle::isAlive).forEach(ProcessHandle::destroyForcibly);
    }

    static boolean isListening(String host, int port) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 500);
            return true;
        } catch (IOException exception) {
            return false;
        }
    }

    /** Walks up from the working directory until the Hotline project root is found. */
    static Path findProjectRoot(Path start) {
        if (start == null) {
            return null;
        }
        Path current = start.toAbsolutePath().normalize();
        while (current != null) {
            if (Files.isRegularFile(current.resolve("main.py")) && Files.isDirectory(current.resolve("python_backend"))) {
                return current;
            }
            current = current.getParent();
        }
        return null;
    }

    /** Returns the interpreter command, or null when no local interpreter is available. */
    static String resolveCommand(Path root, String configured) {
        if (configured != null && !configured.isBlank()) {
            Path candidate = Path.of(configured.trim());
            if (!candidate.isAbsolute()) {
                candidate = root.resolve(candidate);
            }
            return Files.isRegularFile(candidate) ? candidate.toString() : null;
        }
        for (String relative : VENV_EXECUTABLES) {
            Path candidate = root.resolve(relative);
            if (Files.isRegularFile(candidate)) {
                return candidate.toString();
            }
        }
        return null;
    }

    /** Reads the jar path from a code source location such as "jar:nested:/path/app.jar/!/BOOT-INF/classes/!/". */
    static Path parseCodeSourceLocation(String location) {
        if (location == null) {
            return null;
        }
        Matcher matcher = Pattern.compile("(?<![A-Za-z0-9])((?:[A-Za-z]:)?/(?:[^!]*/)*[^!/]*\\.jar)").matcher(location);
        if (matcher.find()) {
            String jarPath = matcher.group(1);
            if (jarPath.length() > 2 && jarPath.charAt(0) == '/' && Character.isLetter(jarPath.charAt(1))
                    && jarPath.charAt(2) == ':') {
                jarPath = jarPath.substring(1);
            }
            return Path.of(jarPath);
        }
        if (location.startsWith("file:")) {
            try {
                return Path.of(URI.create(location));
            } catch (RuntimeException exception) {
                return null;
            }
        }
        return null;
    }

    private Path resolveRoot() {
        String configured = launch.root();
        if (configured != null && !configured.isBlank()) {
            Path candidate = Path.of(configured.trim());
            if (!candidate.isAbsolute()) {
                candidate = Path.of(System.getProperty("user.dir", ".")).resolve(candidate);
            }
            return Files.isDirectory(candidate) ? candidate : null;
        }
        Path fromWorkingDirectory = findProjectRoot(Path.of(System.getProperty("user.dir", ".")));
        return fromWorkingDirectory != null ? fromWorkingDirectory : findProjectRoot(codeSourceLocation());
    }

    /** Falls back to the deployed code location when the working directory is unrelated to the project. */
    private static Path codeSourceLocation() {
        try {
            var source = PythonProcessLauncher.class.getProtectionDomain().getCodeSource();
            if (source == null || source.getLocation() == null) {
                return null;
            }
            // Executable jars expose "file:/path/app.jar!/BOOT-INF/classes/", which is not a file URI.
            return parseCodeSourceLocation(source.getLocation().toString());
        } catch (Exception exception) {
            return null;
        }
    }

    private boolean awaitPort(String host, int port, Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (isListening(host, port)) {
                return true;
            }
            try {
                Thread.sleep(300);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }
}
