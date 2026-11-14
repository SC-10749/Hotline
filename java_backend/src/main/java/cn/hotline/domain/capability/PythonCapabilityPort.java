package cn.hotline.domain.capability;

import cn.hotline.domain.execution.ExecutionRun;
import cn.hotline.domain.execution.ExecutionSubmission;

import java.util.Map;

public interface PythonCapabilityPort {
    PythonHealth health();

    PythonHealth readiness();

    /** GET /skill/list 封套中的 data（技能目录）。 */
    Map<String, Object> skillCatalog();

    /** GET /harness/overview 原始 JSON。 */
    Map<String, Object> harnessOverview();

    /** POST /execution/runs：创建执行运行。 */
    ExecutionRun createExecutionRun(ExecutionSubmission submission);
}
