package cn.hotline.trigger.http;

import java.util.Map;
import cn.hotline.api.dto.CapabilityOverviewView;
import cn.hotline.application.CapabilityOverviewService;
import cn.hotline.application.CapabilityService;
import cn.hotline.domain.capability.PythonHealth;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CapabilityController {
    private final CapabilityService capabilities;
    private final CapabilityOverviewService overviewService;

    public CapabilityController(CapabilityService capabilities, CapabilityOverviewService overviewService) {
        this.capabilities = capabilities;
        this.overviewService = overviewService;
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

    /** 能力总览：由 capability-overview 场景聚合（三路并行采集 + 合并）。 */
    @GetMapping("/api/v1/capabilities/overview")
    public CapabilityOverviewView overview() {
        return overviewService.overview();
    }
}
