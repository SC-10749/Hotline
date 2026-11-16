package cn.hotline.trigger.http;

import cn.hotline.api.dto.ApiError;
import cn.hotline.application.admission.AdmissionService;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import cn.hotline.infrastructure.config.AdmissionProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Duration;

/**
 * 接入治理过滤器：对纳入治理的路径做黑名单、请求速率与并发租约检查，
 * 拒绝时按统一错误契约返回 403/429，并携带 Retry-After；
 * 放行且占用并发租约的请求在完成后释放租约。
 * 治理管理端点（/api/v1/admission）不经过本过滤器，保证可运维性。
 */
@Component
public class AdmissionFilter extends OncePerRequestFilter {

    private final AdmissionService admissionService;
    private final AdmissionProperties properties;
    private final ClientKeyExtractor clientKeyExtractor;
    private final ObjectMapper objectMapper;

    public AdmissionFilter(AdmissionService admissionService, AdmissionProperties properties,
                           ClientKeyExtractor clientKeyExtractor, ObjectMapper objectMapper) {
        this.admissionService = admissionService;
        this.properties = properties;
        this.clientKeyExtractor = clientKeyExtractor;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        if (!properties.enabled()) {
            return true;
        }
        String path = request.getRequestURI();
        return path.startsWith("/api/v1/admission") || !admissionService.included(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String clientKey = clientKeyExtractor.extract(request);
        AdmissionService.Decision decision;
        try {
            decision = admissionService.check(clientKey, request.getRequestURI());
        } catch (AdmissionStoreUnavailableException exception) {
            deny(response, HttpStatus.SERVICE_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE",
                    "接入治理依赖暂不可用", Duration.ofSeconds(5));
            return;
        }
        if (!decision.allowed()) {
            switch (decision.reason()) {
                case BLACKLIST -> deny(response, HttpStatus.FORBIDDEN, "FORBIDDEN",
                        "当前客户端已被限制访问", null);
                case RATE_LIMIT -> deny(response, HttpStatus.TOO_MANY_REQUESTS, "QUOTA_EXCEEDED",
                        "请求过于频繁，请稍后重试", decision.retryAfter());
                case CONCURRENCY -> deny(response, HttpStatus.TOO_MANY_REQUESTS, "QUEUE_FULL",
                        "在途请求过多，请稍后重试", decision.retryAfter());
            }
            return;
        }
        try {
            filterChain.doFilter(request, response);
        } finally {
            admissionService.release(decision);
        }
    }

    private void deny(HttpServletResponse response, HttpStatus status, String code, String message,
                      Duration retryAfter) throws IOException {
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        if (retryAfter != null) {
            long seconds = Math.max(1L, (retryAfter.toMillis() + 999L) / 1000L);
            response.setHeader("Retry-After", String.valueOf(seconds));
        }
        objectMapper.writeValue(response.getWriter(), new ApiError(code, message));
    }
}
