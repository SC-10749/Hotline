package cn.hotline.application.admission;

import cn.hotline.infrastructure.config.AdmissionProperties;
import org.springframework.stereotype.Component;

/**
 * 客户端身份解析：当前版本 Java 侧尚无认证体系，客户端键的取值优先级为
 * 显式 Header（默认 X-Hotline-User，形如登录用户名）→ X-Forwarded-For
 * 首个地址（仅 trust-forwarded-for=true 时采信）→ TCP 远端地址。
 * 解析结果形如 "user:alice" 或 "ip:10.0.0.8"，作为限流与黑名单的维度键。
 */
@Component
public class ClientIdentityResolver {

    private final AdmissionProperties properties;

    public ClientIdentityResolver(AdmissionProperties properties) {
        this.properties = properties;
    }

    public String resolve(String remoteAddress, String clientHeaderValue, String forwardedFor) {
        String fromHeader = sanitize(clientHeaderValue);
        if (fromHeader != null) {
            return "user:" + fromHeader;
        }
        if (properties.trustForwardedFor()) {
            String forwarded = firstForwardedFor(forwardedFor);
            if (forwarded != null) {
                return "ip:" + forwarded;
            }
        }
        String remote = sanitize(remoteAddress);
        return remote == null ? "ip:unknown" : "ip:" + remote;
    }

    private String firstForwardedFor(String forwardedFor) {
        if (forwardedFor == null) {
            return null;
        }
        for (String candidate : forwardedFor.split(",")) {
            String sanitized = sanitize(candidate);
            if (sanitized != null) {
                return sanitized;
            }
        }
        return null;
    }

    /** 去除空白并拒绝超长或含控制字符的取值，避免键污染与存储滥用。 */
    private String sanitize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.isEmpty() || trimmed.length() > properties.maxClientHeaderLength()) {
            return null;
        }
        for (int index = 0; index < trimmed.length(); index++) {
            char character = trimmed.charAt(index);
            if (character < 0x20 || character == 0x7F) {
                return null;
            }
        }
        return trimmed;
    }
}
