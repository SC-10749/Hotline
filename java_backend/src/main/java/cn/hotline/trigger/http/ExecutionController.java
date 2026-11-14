package cn.hotline.trigger.http;

import cn.hotline.api.dto.ExecutionRequestPayload;
import cn.hotline.application.execution.ExecutionSubmissionService;
import cn.hotline.domain.execution.ExecutionSubmissionResult;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 执行提交入口：受理后返回 202 与申请/运行引用，编排细节由 execution-submit 场景承载。 */
@RestController
public class ExecutionController {

    private final ExecutionSubmissionService submissionService;
    private final ClientKeyExtractor clientKeyExtractor;

    public ExecutionController(ExecutionSubmissionService submissionService, ClientKeyExtractor clientKeyExtractor) {
        this.submissionService = submissionService;
        this.clientKeyExtractor = clientKeyExtractor;
    }

    @PostMapping("/api/v1/execution/requests")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ExecutionSubmissionResult submit(@Valid @RequestBody ExecutionRequestPayload payload,
                                            HttpServletRequest request) {
        return submissionService.submit(payload.toSubmission(), clientKeyExtractor.extract(request));
    }
}
