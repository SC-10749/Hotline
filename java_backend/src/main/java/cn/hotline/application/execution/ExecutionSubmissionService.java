package cn.hotline.application.execution;

import cn.hotline.application.flow.FlowEngine;
import cn.hotline.domain.execution.ExecutionRun;
import cn.hotline.domain.execution.ExecutionSubmission;
import cn.hotline.domain.execution.ExecutionSubmissionResult;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Service;

import java.util.UUID;

/**
 * 执行提交入口：生成申请 ID 后驱动 execution-submit 场景——
 * 校验/配额与建运行按 order 分组执行（见 resources/flow/flows.json）。
 */
@Service
public class ExecutionSubmissionService {

    private final FlowEngine flowEngine;

    public ExecutionSubmissionService(FlowEngine flowEngine) {
        this.flowEngine = flowEngine;
    }

    public ExecutionSubmissionResult submit(ExecutionSubmission submission, String clientKey) {
        String requestId = UUID.randomUUID().toString();
        FlowContext context = new FlowContext(FlowKeys.SCENE_EXECUTION_SUBMIT);
        context.put(FlowKeys.SUBMISSION, submission);
        context.put(FlowKeys.CLIENT_KEY, clientKey);
        context.put(FlowKeys.REQUEST_ID, requestId);
        flowEngine.execute(FlowKeys.SCENE_EXECUTION_SUBMIT, context);
        ExecutionRun run = context.require(FlowKeys.EXECUTION_RUN, ExecutionRun.class);
        return new ExecutionSubmissionResult(requestId, run.runId(), run.status());
    }
}
