const solace = require("solclientjs").debug;

solace.SolclientFactory.init({
  profile: solace.SolclientFactoryProfiles.version10,
  logLevel: solace.LogLevel.WARN,
});

const topics = JSON.parse(process.env.SOLACE_TOPICS_JSON || "[]");
const session = solace.SolclientFactory.createSession(
  {
    url: process.env.SOLACE_BROKER_URL,
    vpnName: process.env.SOLACE_VPN,
    userName: process.env.SOLACE_USERNAME,
    password: process.env.SOLACE_PASSWORD,
    connectRetries: 1,
    reconnectRetries: 20,
    reconnectRetryWaitInMsecs: 3000,
  },
  new solace.MessageRxCBInfo((_, message) => {
    const body = message.getBinaryAttachment() ? message.getBinaryAttachment().toString() : "";
    let payload = { raw: body };
    try {
      payload = body ? JSON.parse(body) : {};
    } catch (_error) {}
    const correlationId =
      (message.getCorrelationId && message.getCorrelationId()) ||
      payload.correlationId ||
      "unknown";
    process.stdout.write(
      JSON.stringify({
        type: "message",
        correlationId,
        topicName: message.getDestination()?.getName?.() || null,
        payload,
      }) + "\n",
    );
  }, null),
  new solace.SessionEventCBInfo((activeSession, event) => {
    if (event.sessionEventCode === solace.SessionEventCode.UP_NOTICE) {
      for (const topic of topics) {
        activeSession.subscribe(
          solace.SolclientFactory.createTopicDestination(topic),
          true,
          `spec2event-${topic}`,
          10000,
        );
      }
      process.stdout.write(JSON.stringify({ type: "ready", topics }) + "\n");
      return;
    }
    if (event.sessionEventCode === solace.SessionEventCode.CONNECT_FAILED_ERROR) {
      process.stdout.write(
        JSON.stringify({ type: "error", stage: "connect", info: event.infoStr }) + "\n",
      );
      process.exit(1);
    }
  }, null),
);

session.connect();
