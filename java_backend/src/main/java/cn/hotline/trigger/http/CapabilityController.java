package cn.hotline.trigger.http;

import java.util.Map;
import cn.hotline.application.CapabilityService;
import cn.hotline.domain.capability.PythonHealth;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CapabilityController {
    private final CapabilityService capabilities;

    public CapabilityController(CapabilityService capabilities) {
        this.capabilities = capabilities;
    }

    @GetMapping("/health/live")
    public Map<String, String> live() {
        return Map.of("status", "UP", "service", "hotline-java-api");
    }

    @GetMapping("/health/ready")
    public Map<String, Object> ready() {
        return Map.of("status", "UP", "service", "hotline-java-api",
                "python", capabilities.pythonReadiness());
    }

    @GetMapping("/api/v1/capabilities/python/health")
    public PythonHealth pythonHealth() {
        return capabilities.pythonHealth();
    }
}
