package cn.hotline.application.flow;

import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowExecutionException;
import cn.hotline.domain.flow.FlowScene;
import cn.hotline.domain.flow.FlowTask;
import cn.hotline.domain.flow.OrderGrouping;
import cn.hotline.infrastructure.flow.FlowSceneRegistry;
import cn.hotline.infrastructure.flow.FlowThreadPool;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * 流程引擎：按 order 分组执行场景任务——相同 order 的任务并行，组间串行。
 * 对应 pandora-search-music 的 CompositeItemProcessor：组内多个任务提交到
 * Abtest-task-pool 并行并等待全部完成（allOf 屏障），单任务组直接在当前
 * 线程串行执行；任务通过共享的 {@link FlowContext} 交换结果。
 * 任务失败按声明顺序抛出首个原始异常（业务异常不包装），后续分组不再执行。
 */
public class FlowEngine {

    private static final Logger log = LoggerFactory.getLogger(FlowEngine.class);

    private final FlowSceneRegistry registry;
    private final FlowThreadPool threadPool;

    public FlowEngine(FlowSceneRegistry registry, FlowThreadPool threadPool) {
        this.registry = registry;
        this.threadPool = threadPool;
    }

    public FlowContext execute(String sceneKey, FlowContext context) {
        FlowScene scene = registry.scene(sceneKey);
        try {
            for (List<FlowTask> group : OrderGrouping.group(scene.tasks())) {
                if (group.size() == 1) {
                    runTask(sceneKey, group.get(0), context);
                } else {
                    runGroup(sceneKey, group, context);
                }
            }
        } finally {
            log.debug("流程场景 {} 执行结束：flowId={}，耗时 {} ms", sceneKey, context.flowId(), context.elapsedMillis());
        }
        return context;
    }

    private void runTask(String sceneKey, FlowTask task, FlowContext context) {
        try {
            task.processor().process(context, task.params());
        } catch (RuntimeException | Error exception) {
            log.warn("流程场景 {} 任务 {} 执行失败：{}", sceneKey, task.key(), exception.getMessage());
            throw exception;
        } catch (Exception exception) {
            log.warn("流程场景 {} 任务 {} 执行失败：{}", sceneKey, task.key(), exception.getMessage());
            throw new FlowExecutionException("场景 " + sceneKey + " 任务 " + task.key() + " 执行失败", exception);
        }
    }

    private void runGroup(String sceneKey, List<FlowTask> group, FlowContext context) {
        Throwable[] failures = new Throwable[group.size()];
        List<CompletableFuture<Void>> futures = new ArrayList<>(group.size());
        for (int index = 0; index < group.size(); index++) {
            FlowTask task = group.get(index);
            int slot = index;
            futures.add(CompletableFuture.runAsync(() -> {
                try {
                    task.processor().process(context, task.params());
                } catch (Throwable throwable) {
                    failures[slot] = throwable;
                }
            }, threadPool.executor()));
        }
        futures.forEach(CompletableFuture::join);
        for (int index = 0; index < failures.length; index++) {
            if (failures[index] != null) {
                FlowTask failed = group.get(index);
                log.warn("流程场景 {} 任务 {} 并行执行失败：{}", sceneKey, failed.key(), failures[index].getMessage());
                rethrow(failures[index], sceneKey, failed);
            }
        }
    }

    private void rethrow(Throwable throwable, String sceneKey, FlowTask task) {
        if (throwable instanceof RuntimeException runtimeException) {
            throw runtimeException;
        }
        if (throwable instanceof Error error) {
            throw error;
        }
        throw new FlowExecutionException("场景 " + sceneKey + " 任务 " + task.key() + " 执行失败", throwable);
    }
}
