package cn.hotline.application.flow;

import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowItemProcessor;
import cn.hotline.domain.flow.FlowNotFoundException;
import cn.hotline.infrastructure.config.FlowProperties;
import cn.hotline.infrastructure.flow.FlowProcessorFactory;
import cn.hotline.infrastructure.flow.FlowSceneRegistry;
import cn.hotline.infrastructure.flow.FlowThreadPool;
import cn.hotline.infrastructure.flow.FunctionMappings;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ByteArrayResource;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class FlowEngineTest {

    private static final List<String> EVENTS = new CopyOnWriteArrayList<>();

    private static final String SCENES = """
            {
              "serial-test": {
                "first": {"order": "0", "fmap": "flow_1", "value": "v1"},
                "second": {"order": "1", "fmap": "flow_2"},
                "third": {"order": "2", "fmap": "flow_3"}
              },
              "parallel-test": {
                "parallel-a": {"order": "0", "fmap": "flow_4"},
                "parallel-b": {"order": "0", "fmap": "flow_4"},
                "parallel-c": {"order": "0", "fmap": "flow_4"},
                "after": {"order": "1", "fmap": "flow_3"}
              },
              "toggle-test": {
                "skipped": {"order": "0", "fmap": "flow_3", "toggle": "0"},
                "kept": {"order": "1", "fmap": "flow_3"}
              },
              "param-test": {
                "task": {"order": "0", "fmap": "flow_6", "name": "x", "count": "5", "flag": "true"}
              },
              "failure-test": {
                "boom": {"order": "0", "fmap": "flow_5"},
                "never": {"order": "1", "fmap": "flow_3"}
              },
              "parallel-failure-test": {
                "ok": {"order": "0", "fmap": "flow_3"},
                "boom": {"order": "0", "fmap": "flow_5"}
              }
            }
            """;

    private FlowThreadPool pool;
    private FlowEngine engine;

    @BeforeEach
    void setUp() {
        EVENTS.clear();
        pool = new FlowThreadPool(new FlowProperties.Pool(2, 8, Duration.ofSeconds(30)));
        engine = new FlowEngine(registry(), pool);
    }

    @AfterEach
    void tearDown() {
        pool.close();
    }

    @Test
    void serialTasksRunInTheCallingThreadAndShareTheContext() {
        String callingThread = Thread.currentThread().getName();

        engine.execute("serial-test", new FlowContext("serial-test"));

        assertThat(EVENTS).containsExactly("produce:v1", "consume:v1", "thread:" + callingThread, "third");
    }

    @Test
    void parallelGroupRunsOnPoolThreadsAndWaitsBeforeTheNextOrder() {
        engine.execute("parallel-test", new FlowContext("parallel-test"));

        assertThat(EVENTS).hasSize(4);
        assertThat(EVENTS.get(3)).isEqualTo("after");
        List<String> parallel = EVENTS.subList(0, 3);
        assertThat(parallel).allSatisfy(event -> assertThat(event).contains("@hotline-flow-"));
        assertThat(parallel.stream().map(event -> event.substring(event.indexOf('@'))).distinct()).hasSize(3);
    }

    @Test
    void toggleDisabledTaskIsSkipped() {
        engine.execute("toggle-test", new FlowContext("toggle-test"));
        assertThat(EVENTS).containsExactly("kept");
    }

    @Test
    void taskParamsReachTheProcessorHelpers() {
        engine.execute("param-test", new FlowContext("param-test"));
        assertThat(EVENTS).containsExactly("params:x,5,true");
    }

    @Test
    void failurePropagatesOriginalExceptionAndStopsLaterOrders() {
        assertThatThrownBy(() -> engine.execute("failure-test", new FlowContext("failure-test")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("boom");
        assertThat(EVENTS).doesNotContain("never");
    }

    @Test
    void parallelFailurePropagatesOriginalException() {
        assertThatThrownBy(() -> engine.execute("parallel-failure-test", new FlowContext("parallel-failure-test")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("boom");
    }

    @Test
    void unknownSceneFailsFast() {
        assertThatThrownBy(() -> engine.execute("missing-scene", new FlowContext("missing-scene")))
                .isInstanceOf(FlowNotFoundException.class);
    }

    private static FlowSceneRegistry registry() {
        Properties mappings = new Properties();
        mappings.setProperty("flow_1", ProducerProcessor.class.getName());
        mappings.setProperty("flow_2", ConsumerProcessor.class.getName());
        mappings.setProperty("flow_3", ToggleAwareProcessor.class.getName());
        mappings.setProperty("flow_4", ParallelProcessor.class.getName());
        mappings.setProperty("flow_5", BoomProcessor.class.getName());
        mappings.setProperty("flow_6", ParamProcessor.class.getName());
        ApplicationContext applicationContext = mock(ApplicationContext.class);
        when(applicationContext.getBeanNamesForType(any(Class.class), anyBoolean(), anyBoolean()))
                .thenReturn(new String[0]);
        return new FlowSceneRegistry(
                new ByteArrayResource(SCENES.getBytes(StandardCharsets.UTF_8)),
                FunctionMappings.of(mappings),
                new FlowProcessorFactory(applicationContext),
                new ObjectMapper());
    }

    public static final class ProducerProcessor implements FlowItemProcessor {
        @Override
        public void process(FlowContext context, Map<String, Object> params) {
            context.put("produced", String.valueOf(params.get("value")));
            EVENTS.add("produce:" + params.get("value"));
        }
    }

    public static final class ConsumerProcessor implements FlowItemProcessor {
        @Override
        public void process(FlowContext context, Map<String, Object> params) {
            EVENTS.add("consume:" + context.require("produced", String.class));
            EVENTS.add("thread:" + Thread.currentThread().getName());
        }
    }

    public static final class ToggleAwareProcessor extends AbstractFlowProcessor {
        @Override
        protected void doProcess(FlowContext context, Map<String, Object> params) {
            EVENTS.add(String.valueOf(params.get("_task")));
        }
    }

    public static final class ParallelProcessor implements FlowItemProcessor {
        @Override
        public void process(FlowContext context, Map<String, Object> params) throws InterruptedException {
            Thread.sleep(120);
            EVENTS.add("parallel:" + params.get("_task") + "@" + Thread.currentThread().getName());
        }
    }

    public static final class BoomProcessor implements FlowItemProcessor {
        @Override
        public void process(FlowContext context, Map<String, Object> params) {
            throw new IllegalStateException("boom");
        }
    }

    public static final class ParamProcessor extends AbstractFlowProcessor {
        @Override
        protected void doProcess(FlowContext context, Map<String, Object> params) {
            EVENTS.add("params:" + stringParam(params, "name", "none")
                    + "," + intParam(params, "count", 1)
                    + "," + booleanParam(params, "flag", false));
        }
    }
}
