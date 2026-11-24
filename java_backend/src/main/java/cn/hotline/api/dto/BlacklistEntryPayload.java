package cn.hotline.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** 黑名单条目载荷（POST /api/v1/admission/blacklist）。 */
public record BlacklistEntryPayload(
        @NotBlank(message = "entry 不能为空")
        @Pattern(regexp = "^(ip|user):\\S+$", message = "entry 需要形如 ip:1.2.3.4 或 user:someone")
        String entry) {
}
