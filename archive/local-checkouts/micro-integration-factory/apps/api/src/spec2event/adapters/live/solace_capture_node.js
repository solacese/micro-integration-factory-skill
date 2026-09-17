const solace = require("solclientjs").debug;

solace.SolclientFactory.init({
  profile: solace.SolclientFactoryProfiles.version10,
  logLevel: solace.LogLevel.WARN,
});

function parsePayload(message) {
  const body = message.getBinaryAttachment() ? message.getBinaryAttachment().toString() : "";
  if (!body) {
    return {};
  }
  try {
    return JSON.parse(body);
  } catch (_error) {
    return { raw: body };
  }
}

const topicFilter = process.env.SOLACE_TOPIC_FILTER;
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
    process.stdout.write(
      JSON.stringify({
        type: "message",
        topicName: message.getDestination()?.getName?.() || topicFilter,
        headers: {
          correlationId: message.getCorrelationId?.() || null,
          applicationMessageId: message.getApplicationMessageId?.() || null,
        },
        payload: parsePayload(message),
      }) + "\n",
    );
  }, null),
  new solace.SessionEventCBInfo((activeSession, event) => {
    if (event.sessionEventCode === solace.SessionEventCode.UP_NOTICE) {
      activeSession.subscribe(
        solace.SolclientFactory.createTopicDestination(topicFilter),
        true,
        `mif-${topicFilter}`,
        10000,
      );
      process.stdout.write(JSON.stringify({ type: "ready", topicFilter }) + "\n");
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
