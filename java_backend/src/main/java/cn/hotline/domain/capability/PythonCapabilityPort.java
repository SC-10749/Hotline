package cn.hotline.domain.capability;

public interface PythonCapabilityPort {
    PythonHealth health();

    PythonHealth readiness();
}
