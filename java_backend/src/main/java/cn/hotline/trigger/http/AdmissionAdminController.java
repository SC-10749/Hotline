package cn.hotline.trigger.http;

import cn.hotline.api.dto.BlacklistEntryPayload;
import cn.hotline.domain.admission.AdmissionStore;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 治理管理端点：查询存储类型与黑名单、增删黑名单条目。
 * 当前版本未接入认证（见 README 规划），部署时应仅在管理网络暴露。
 */
@RestController
@RequestMapping("/api/v1/admission")
public class AdmissionAdminController {

    private final AdmissionStore admissionStore;

    public AdmissionAdminController(AdmissionStore admissionStore) {
        this.admissionStore = admissionStore;
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("store", admissionStore.getClass().getSimpleName());
        view.put("blacklist", sortedBlacklist());
        return view;
    }

    @PostMapping("/blacklist")
    public Map<String, Object> add(@Valid @RequestBody BlacklistEntryPayload payload) {
        admissionStore.addToBlacklist(payload.entry());
        return result(true);
    }

    @DeleteMapping("/blacklist")
    public Map<String, Object> remove(@RequestParam(required = false) String entry) {
        if (entry == null || entry.isBlank()) {
            return result(false);
        }
        return result(admissionStore.removeFromBlacklist(entry.trim()));
    }

    private Map<String, Object> result(boolean success) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("success", success);
        view.put("blacklist", sortedBlacklist());
        return view;
    }

    private List<String> sortedBlacklist() {
        return admissionStore.blacklist().stream().sorted().toList();
    }
}
