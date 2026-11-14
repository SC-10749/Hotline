package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import org.springframework.core.io.Resource;

import java.io.IOException;
import java.io.InputStream;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/**
 * funcmap 映射：fmap 键（如 flow_1）到处理器全限定类名。
 * 写法沿用 pandora-search-music 的 rec_funcmaps.properties：
 * {@code flow_1=cn.hotline.application.flow.task.SomeProcessor}。
 */
public final class FunctionMappings {

    private final Map<String, String> mappings;

    private FunctionMappings(Map<String, String> mappings) {
        this.mappings = Collections.unmodifiableMap(mappings);
    }

    public static FunctionMappings of(Properties properties) {
        Map<String, String> parsed = new LinkedHashMap<>();
        for (String name : properties.stringPropertyNames()) {
            String value = properties.getProperty(name);
            if (value == null || value.isBlank()) {
                throw new FlowConfigurationException("funcmap 配置为空：" + name);
            }
            parsed.put(name.trim(), value.trim());
        }
        if (parsed.isEmpty()) {
            throw new FlowConfigurationException("funcmap 配置未包含任何映射");
        }
        return new FunctionMappings(parsed);
    }

    public static FunctionMappings load(Resource resource) {
        Properties properties = new Properties();
        try (InputStream input = resource.getInputStream()) {
            properties.load(input);
        } catch (IOException exception) {
            throw new FlowConfigurationException("读取 funcmap 配置失败：" + resource.getDescription(), exception);
        }
        return of(properties);
    }

    public String className(String fmapKey) {
        String className = mappings.get(fmapKey);
        if (className == null) {
            throw new FlowConfigurationException("funcmap 未配置映射键：" + fmapKey);
        }
        return className;
    }

    /** 沿用 pandora getFMapIndex 约定：取第一个下划线之后的部分解析为整数。 */
    public static int indexOf(String fmapKey) {
        int separator = fmapKey.indexOf('_');
        if (separator < 0 || separator == fmapKey.length() - 1) {
            throw new FlowConfigurationException("fmap 键缺少下划线序号：" + fmapKey);
        }
        try {
            return Integer.parseInt(fmapKey.substring(separator + 1));
        } catch (NumberFormatException exception) {
            throw new FlowConfigurationException("fmap 键序号不是整数：" + fmapKey);
        }
    }

    public Set<String> keys() {
        return mappings.keySet();
    }
}
