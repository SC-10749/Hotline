package cn.hotline.application.flow.task;

import cn.hotline.application.admission.SubmissionLedger;
import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.Map;

/** 提交台账记录：运行创建成功后按客户端累计当日提交次数（尽力而为，不阻断已受理的提交）。 */
@Component
public class SubmissionLedgerProcessor extends AbstractFlowProcessor {

    private final SubmissionLedger submissionLedger;

    public SubmissionLedgerProcessor(SubmissionLedger submissionLedger) {
        this.submissionLedger = submissionLedger;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        String clientKey = context.require(FlowKeys.CLIENT_KEY, String.class);
        submissionLedger.record(clientKey);
    }
}
