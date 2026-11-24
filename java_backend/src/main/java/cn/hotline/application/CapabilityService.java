package cn.hotline.application;

import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonHealth;
import org.springframework.stereotype.Service;

@Service
public class CapabilityService {
    private final PythonCapabilityPort python;

    public CapabilityService(PythonCapabilityPort python) {
        this.python = python;
    }

    public PythonHealth pythonHealth() {
        return python.health();
    }

    public PythonHealth pythonReadiness() {
        return python.readiness();
    }
}
