package cn.hotline.trigger.http;

import cn.hotline.application.admission.ClientIdentityResolver;
import cn.hotline.infrastructure.config.AdmissionProperties;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;

/** 从 HTTP 请求解析治理维度键（过滤器与业务控制器共用，保证同一请求口径一致）。 */
@Component
public class ClientKeyExtractor {

    private final AdmissionProperties properties;
    private final ClientIdentityResolver resolver;

    public ClientKeyExtractor(AdmissionProperties properties, ClientIdentityResolver resolver) {
        this.properties = properties;
        this.resolver = resolver;
    }

    public String extract(HttpServletRequest request) {
        return resolver.resolve(
                request.getRemoteAddr(),
                request.getHeader(properties.clientHeader()),
                request.getHeader("X-Forwarded-For"));
    }
}
