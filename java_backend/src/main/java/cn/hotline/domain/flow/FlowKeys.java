package cn.hotline.domain.flow;

/** 场景键与上下文键约定。 */
public final class FlowKeys {

    /** 场景：能力总览聚合。 */
    public static final String SCENE_CAPABILITY_OVERVIEW = "capability-overview";
    /** 场景：执行提交。 */
    public static final String SCENE_EXECUTION_SUBMIT = "execution-submit";

    /** 上下文：提交请求（ExecutionSubmission）。 */
    public static final String SUBMISSION = "submission";
    /** 上下文：客户端键（ClientIdentityResolver 的产物）。 */
    public static final String CLIENT_KEY = "clientKey";
    /** 上下文：提交申请 ID（Java 生成）。 */
    public static final String REQUEST_ID = "requestId";
    /** 上下文：Python 运行引用（ExecutionRun）。 */
    public static final String EXECUTION_RUN = "executionRun";
    /** 上下文：提交结果（ExecutionSubmissionResult）。 */
    public static final String SUBMISSION_RESULT = "submissionResult";

    /** 上下文：Python 健康状态。 */
    public static final String PYTHON_STATUS = "pythonStatus";
    /** 上下文：技能目录。 */
    public static final String SKILL_CATALOG = "skillCatalog";
    /** 上下文：自动化总览。 */
    public static final String HARNESS_OVERVIEW = "harnessOverview";
    /** 上下文：能力总览结果（CapabilityOverviewView）。 */
    public static final String OVERVIEW_RESULT = "overviewResult";

    private FlowKeys() {
    }
}
