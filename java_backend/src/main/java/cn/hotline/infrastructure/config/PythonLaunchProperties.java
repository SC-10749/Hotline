package cn.hotline.infrastructure.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/** Local development settings for starting the Python sidecar next to the Java process. */
@Validated
@ConfigurationProperties("hotline.python.launch")
public record PythonLaunchProperties(
        boolean enabled,
        String executable,
        String root,
        Duration startupTimeout) {

    public PythonLaunchProperties {
        if (startupTimeout != null && !startupTimeout.isPositive()) {
            throw new IllegalArgumentException("Python startup timeout must be positive");
        }
    }
}
