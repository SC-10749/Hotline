package cn.hotline.infrastructure.launch;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class PythonProcessLauncherTest {

    @TempDir
    Path temp;

    @Test
    void findsTheProjectRootFromANestedWorkingDirectory() throws IOException {
        Path root = Files.createDirectories(temp.resolve("repo"));
        Files.writeString(root.resolve("main.py"), "");
        Files.createDirectories(root.resolve("python_backend"));
        Path nested = Files.createDirectories(root.resolve("java_backend"));

        assertThat(PythonProcessLauncher.findProjectRoot(nested)).isEqualTo(root.toAbsolutePath().normalize());
        assertThat(PythonProcessLauncher.findProjectRoot(temp)).isNull();
    }

    @Test
    void prefersTheLocalVirtualEnvironmentInterpreter() throws IOException {
        Path root = Files.createDirectories(temp.resolve("repo"));
        Path interpreter = Files.createDirectories(root.resolve(".venv/Scripts")).resolve("python.exe");
        Files.writeString(interpreter, "");

        assertThat(PythonProcessLauncher.resolveCommand(root, null)).isEqualTo(interpreter.toString());
        assertThat(PythonProcessLauncher.resolveCommand(root, "  ")).isEqualTo(interpreter.toString());
    }

    @Test
    void reportsMissingInterpretersInsteadOfGuessing() throws IOException {
        Path root = Files.createDirectories(temp.resolve("repo"));

        assertThat(PythonProcessLauncher.resolveCommand(root, null)).isNull();
        assertThat(PythonProcessLauncher.resolveCommand(root, "missing/python.exe")).isNull();
    }

    @Test
    void acceptsAnExplicitInterpreterPathRelativeToTheProjectRoot() throws IOException {
        Path root = Files.createDirectories(temp.resolve("repo"));
        Path interpreter = Files.createDirectories(root.resolve("custom")).resolve("python.exe");
        Files.writeString(interpreter, "");

        assertThat(PythonProcessLauncher.resolveCommand(root, "custom/python.exe")).isEqualTo(interpreter.toString());
        assertThat(PythonProcessLauncher.resolveCommand(root, interpreter.toString())).isEqualTo(interpreter.toString());
    }

    @Test
    void stopsTheWholeProcessTree() throws Exception {
        Process child = sleeper();
        List<ProcessHandle> descendants = child.descendants().toList();
        assertThat(descendants).isNotEmpty();

        PythonProcessLauncher.terminateTree(child);

        assertThat(child.isAlive()).isFalse();
        assertThat(descendants).noneMatch(ProcessHandle::isAlive);
    }

    /** A JVM that starts one more JVM, so the tree has a descendant to clean up. */
    private static Process sleeper() throws IOException {
        return new ProcessBuilder(javaBinary(), "-cp", System.getProperty("java.class.path"),
                Sleeper.class.getName()).redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD).start();
    }

    private static String javaBinary() {
        return Path.of(System.getProperty("java.home"), "bin", "java").toString();
    }

    public static final class Sleeper {
        public static void main(String[] args) throws Exception {
            if (args.length == 0) {
                new ProcessBuilder(javaBinary(), "-cp", System.getProperty("java.class.path"),
                        Sleeper.class.getName(), "child").redirectOutput(ProcessBuilder.Redirect.DISCARD)
                        .redirectError(ProcessBuilder.Redirect.DISCARD).start();
            }
            Thread.sleep(120_000);
        }
    }

    @Test
    void readsTheJarLocationOutOfAnExecutableJarLocation() {
        Path parsed = PythonProcessLauncher.parseCodeSourceLocation(
                "jar:nested:/F:/Hotline/java_backend/target/app.jar/!BOOT-INF/classes/!/");

        assertThat(parsed).isNotNull();
        assertThat(parsed.toString()).endsWith("app.jar");
        assertThat(PythonProcessLauncher.parseCodeSourceLocation("file:/F:/Hotline/java_backend/target/classes/"))
                .isNotNull()
                .satisfies(path -> assertThat(path.toString()).contains("Hotline"));
    }

    @Test
    void detectsWhetherThePythonPortIsAlreadyListening() throws IOException {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress("127.0.0.1", 0));
            assertThat(PythonProcessLauncher.isListening("127.0.0.1", server.getLocalPort())).isTrue();
            int closedPort = server.getLocalPort();
            server.close();
            assertThat(PythonProcessLauncher.isListening("127.0.0.1", closedPort)).isFalse();
        }
    }
}
