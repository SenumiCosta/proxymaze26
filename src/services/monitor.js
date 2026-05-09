const state = require('../store/state');
const probeRunner = require('./probeRunner');
const alertEngine = require('./alertEngine');

const STUCK_TIMEOUT_MS = 60000; // Safety: reset running flag after 60s
const MIN_CATCH_UP_GAP_MS = 250;

class Monitor {
  constructor() {
    this.intervalId = null;
    this.running = false;
    this.runStartedAt = 0;
    this.currentRun = null;
    this.lastCompletedAt = 0;
    this.lastCatchUpAt = 0;
    this.started = false;
  }

  start() {
    if (this.started) return;
    this.started = true;
    this.scheduleInterval();
  }

  restart() {
    this.scheduleInterval();
  }

  scheduleInterval() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
    }
    const ms = state.config.check_interval_seconds * 1000;
    this.intervalId = setInterval(() => this.runCheckCycle(), ms);
  }

  triggerImmediate() {
    this.lastCompletedAt = 0;
    setImmediate(() => this.runCheckCycle());
  }

  hasPendingProxies() {
    return Array.from(state.proxies.values()).some(proxy => proxy.status === 'pending' || !proxy.last_checked_at);
  }

  isDue() {
    if (state.proxies.size === 0) return false;
    if (this.hasPendingProxies()) return true;
    if (this.lastCompletedAt === 0) return true;

    const intervalMs = state.config.check_interval_seconds * 1000;
    return Date.now() - this.lastCompletedAt >= intervalMs;
  }

  async ensureFresh() {
    if (!this.isDue()) return;

    const now = Date.now();
    if (now - this.lastCatchUpAt < MIN_CATCH_UP_GAP_MS && this.currentRun) {
      await this.currentRun;
      return;
    }

    this.lastCatchUpAt = now;
    await this.runCheckCycle();
  }

  async runCheckCycle() {
    // Safety: if running flag has been stuck for over 60s, force-reset it
    if (this.running && (Date.now() - this.runStartedAt) > STUCK_TIMEOUT_MS) {
      this.running = false;
      this.currentRun = null;
    }
    if (this.running) return this.currentRun;

    this.running = true;
    this.runStartedAt = Date.now();
    this.currentRun = (async () => {
      const proxies = Array.from(state.proxies.values());
      if (proxies.length > 0) {
        await probeRunner.probeAll(proxies);
      }
      alertEngine.evaluate();
      this.lastCompletedAt = Date.now();
    })();

    try {
      await this.currentRun;
    } catch (err) {
      console.error('[Monitor] Check cycle error:', err.message);
    } finally {
      this.running = false;
      this.currentRun = null;
    }
  }
}

module.exports = new Monitor();
