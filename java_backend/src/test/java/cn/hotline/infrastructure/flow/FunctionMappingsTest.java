package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FunctionMappingsTest {

    @Test
    void indexFollowsPandoraConvention() {
        assertThat(FunctionMappings.indexOf("flow_1")).isEqualTo(1);
        assertThat(FunctionMappings.indexOf("flow_42")).isEqualTo(42);
    }

    @Test
    void invalidIndexIsRejected() {
        assertThatThrownBy(() -> FunctionMappings.indexOf("flow")).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> FunctionMappings.indexOf("flow_")).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> FunctionMappings.indexOf("flow_x")).isInstanceOf(FlowConfigurationException.class);
        // 索引取第一个下划线之后的部分，键名中含下划线时同样按该约定解析失败
        assertThatThrownBy(() -> FunctionMappings.indexOf("rec_funcmaps_42"))
                .isInstanceOf(FlowConfigurationException.class);
    }

    @Test
    void classNameLookupRejectsMissingKey() {
        FunctionMappings mappings = mappings("flow_1", "cn.example.One");
        assertThat(mappings.className("flow_1")).isEqualTo("cn.example.One");
        assertThat(mappings.keys()).containsExactly("flow_1");
        assertThatThrownBy(() -> mappings.className("flow_9"))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("flow_9");
    }

    @Test
    void blankValueAndEmptyConfigurationAreRejected() {
        Properties blank = new Properties();
        blank.setProperty("flow_1", "  ");
        assertThatThrownBy(() -> FunctionMappings.of(blank)).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> FunctionMappings.of(new Properties())).isInstanceOf(FlowConfigurationException.class);
    }

    @Test
    void loadsFromResource() {
        FunctionMappings mappings = FunctionMappings.load(
                new ByteArrayResource("flow_1=cn.example.One\n".getBytes(StandardCharsets.UTF_8)));
        assertThat(mappings.className("flow_1")).isEqualTo("cn.example.One");
    }

    private static FunctionMappings mappings(String key, String className) {
        Properties properties = new Properties();
        properties.setProperty(key, className);
        return FunctionMappings.of(properties);
    }
}
