// One request per scheduled run: ask the Sprite to start the build script, which detaches and returns.
const EXEC = "https://api.sprites.dev/v1/sprites/brave-indigo-lion/exec?cmd=bash&cmd=/home/sprite/station/scripts/start_build.sh";

export default {
  async scheduled(controller, env, ctx) {
    const res = await fetch(EXEC, { method: "POST", headers: { Authorization: `Bearer ${env.SPRITES_TOKEN}` } });
    const body = (await res.text()).slice(0, 200);
    console.log(`cron ${controller.cron} at ${new Date(controller.scheduledTime).toISOString()}: HTTP ${res.status} ${body}`);
    if (!res.ok) throw new Error(`Sprite exec failed: HTTP ${res.status}`);  // shows as a failure in Past Events
  },
};
