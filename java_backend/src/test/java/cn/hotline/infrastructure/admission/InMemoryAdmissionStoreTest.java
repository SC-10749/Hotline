package cn.hotline.infrastructure.admission;

import cn.hotline.domain.admission.AdmissionStore;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class InMemoryAdmissionStoreTest {

    private final MutableClock clock = new MutableClock();
    private final InMemoryAdmissionStore store = new InMemoryAdmissionStore(clock);

    @Test
    void blacklistAddRemoveAndLookup() {
        assertThat(store.isBlacklisted("user:bad")).isFalse();

        store.addToBlacklist("user:bad");

        assertThat(store.isBlacklisted("user:bad")).isTrue();
        assertThat(store.blacklist()).containsExactly("user:bad");
        assertThat(store.removeFromBlacklist("user:bad")).isTrue();
        assertThat(store.removeFromBlacklist("user:bad")).isFalse();
        assertThat(store.isBlacklisted("user:bad")).isFalse();
    }

    @Test
    void windowCountsWithinWindowAndResetsAfterwards() {
        Duration window = Duration.ofSeconds(10);
        assertThat(store.incrementWindow("rate:user:a", window).count()).isEqualTo(1);
        assertThat(store.incrementWindow("rate:user:a", window).count()).isEqualTo(2);
        assertThat(store.incrementWindow("rate:user:a", window).count()).isEqualTo(3);

        clock.advance(window);

        AdmissionStore.RateCount reset = store.incrementWindow("rate:user:a", window);
        assertThat(reset.count()).isEqualTo(1);
        assertThat(reset.retryAfter()).isEqualTo(window);
    }

    @Test
    void leaseLimitReleaseAndExpiry() {
        Duration lease = Duration.ofSeconds(30);
        Optional<String> first = store.acquireLease("lease:user:a", 1, lease, "user:a");
        assertThat(first).isPresent();
        assertThat(store.acquireLease("lease:user:a", 1, lease, "user:a")).isEmpty();

        store.releaseLease("lease:user:a", first.get());
        assertThat(store.acquireLease("lease:user:a", 1, lease, "user:a")).isPresent();

        // 未释放的租约到期后自动空出名额
        assertThat(store.acquireLease("lease:user:b", 1, lease, "user:b")).isPresent();
        assertThat(store.acquireLease("lease:user:b", 1, lease, "user:b")).isEmpty();
        clock.advance(Duration.ofSeconds(31));
        assertThat(store.acquireLease("lease:user:b", 1, lease, "user:b")).isPresent();
    }

    @Test
    void countersExpireAfterTtl() {
        Duration ttl = Duration.ofHours(26);
        assertThat(store.incrementCounter("counter:a", ttl)).isEqualTo(1);
        assertThat(store.incrementCounter("counter:a", ttl)).isEqualTo(2);
        assertThat(store.counterValue("counter:a")).isEqualTo(2);

        clock.advance(Duration.ofHours(27));

        assertThat(store.counterValue("counter:a")).isZero();
        assertThat(store.incrementCounter("counter:a", ttl)).isEqualTo(1);
    }

    /** 测试用可拨动时钟。 */
    private static final class MutableClock extends Clock {

        private long millis;

        void advance(Duration duration) {
            millis += duration.toMillis();
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return Instant.ofEpochMilli(millis);
        }
    }
}
