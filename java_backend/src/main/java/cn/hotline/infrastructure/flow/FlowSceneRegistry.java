package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowItemProcessor;
import cn.hotline.domain.flow.FlowNotFoundException;
import cn.hotline.domain.flow.FlowScene;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * 流程场景注册表：启动时加载并解析全部场景与处理器（fail-fast），
 * 配置更新后需重启生效。
 */
public class FlowSceneRegistry {

    private static final Logger log = LoggerFactory.getLogger(FlowSceneRegistry.class);

    private final Map<String, FlowScene> scenes;

    public FlowSceneRegistry(Resource scenesResource, FunctionMappings functionMappings,
                             FlowProcessorFactory processorFactory, ObjectMapper objectMapper) {
        String json = read(scenesResource);
        this.scenes = new FlowSceneParser(objectMapper)
                .parse(json, fmapKey -> processorFactory.resolve(fmapKey, functionMappings.className(fmapKey)));
        scenes.forEach((sceneKey, scene) -> log.info("流程场景已加载：{}（{} 个任务）", sceneKey, scene.tasks().size()));
    }

    public FlowScene scene(String sceneKey) {
        FlowScene scene = scenes.get(sceneKey);
        if (scene == null) {
            throw new FlowNotFoundException("流程场景未配置：" + sceneKey);
        }
        return scene;
    }

    public Map<String, FlowScene> scenes() {
        return scenes;
    }

    private static String read(Resource resource) {
        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new FlowConfigurationException("读取流程配置失败：" + resource.getDescription(), exception);
        }
    }
}
