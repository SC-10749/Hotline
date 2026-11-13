package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowItemProcessor;
import cn.hotline.domain.flow.FlowScene;
import cn.hotline.domain.flow.FlowTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.function.Function;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FlowSceneParserTest {

    private final FlowSceneParser parser = new FlowSceneParser(new ObjectMapper());
    private final Function<String, FlowItemProcessor> resolver = key -> (context, params) -> {
    };

    @Test
    void parsesOrdersParamsAndSortsByOrder() {
        String json = """
                {"scene-a": {
                    "beta": {"order": "2", "fmap": "flow_2"},
                    "alpha": {"order": 0, "fmap": "flow_1", "maxQueryLength": "10", "flag": true, "count": 7}
                }}""";

        Map<String, FlowScene> scenes = parser.parse(json, resolver);

        FlowScene scene = scenes.get("scene-a");
        assertThat(scene.key()).isEqualTo("scene-a");
        assertThat(scene.tasks()).extracting(FlowTask::key).containsExactly("alpha", "beta");
        assertThat(scene.tasks().get(0).order()).isZero();
        assertThat(scene.tasks().get(1).order()).isEqualTo(2);
        Map<String, Object> params = scene.tasks().get(0).params();
        assertThat(params)
                .containsEntry("maxQueryLength", "10")
                .containsEntry("flag", true)
                .containsEntry("count", 7)
                .containsEntry("order", 0)
                .containsEntry("_scene", "scene-a")
                .containsEntry("_task", "alpha");
    }

    @Test
    void invalidOrderReportsSceneAndTaskLocation() {
        assertThatThrownBy(() -> parser.parse("{\"s\": {\"t\": {\"order\": \"x\", \"fmap\": \"flow_1\"}}}", resolver))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("场景 s 任务 t");
        assertThatThrownBy(() -> parser.parse("{\"s\": {\"t\": {\"fmap\": \"flow_1\"}}}", resolver))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("缺少 order");
    }

    @Test
    void missingOrBlankFmapIsRejected() {
        assertThatThrownBy(() -> parser.parse("{\"s\": {\"t\": {\"order\": \"0\"}}}", resolver))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("缺少 fmap");
    }

    @Test
    void resolverFailuresAreWrappedWithLocation() {
        Function<String, FlowItemProcessor> failing = key -> {
            throw new FlowConfigurationException("funcmap 未配置映射键：" + key);
        };
        assertThatThrownBy(() -> parser.parse("{\"s\": {\"t\": {\"order\": \"0\", \"fmap\": \"flow_9\"}}}", failing))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("处理器解析失败")
                .hasMessageContaining("flow_9");
    }

    @Test
    void malformedStructuresAreRejected() {
        assertThatThrownBy(() -> parser.parse("{}", resolver)).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> parser.parse("[]", resolver)).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> parser.parse("not-json", resolver)).isInstanceOf(FlowConfigurationException.class);
        assertThatThrownBy(() -> parser.parse("{\"s\": {}}", resolver))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("非空对象");
        assertThatThrownBy(() -> parser.parse("{\"s\": {\"t\": 3}}", resolver))
                .isInstanceOf(FlowConfigurationException.class)
                .hasMessageContaining("必须是对象");
    }
}
