package com.solace.samples.microintegration;

import com.solace.connector.test.resources.PubSubPlusExtension;
import com.solace.connector.test.resources.resource.ConnectorArgsBuilder;
import com.solace.connector.test.resources.resource.SolaceMessaging;
import com.solace.connector.test.resources.resource.SolaceQueue;
import com.solace.samples.simplequeuing.client.SimpleQueuingClient;
import com.solace.samples.simplequeuing.test.extension.SimpleQueuingExtension;
import com.solacesystems.jcsmp.JCSMPException;
import com.solacesystems.jcsmp.JCSMPFactory;
import com.solacesystems.jcsmp.Queue;
import com.solacesystems.jcsmp.TextMessage;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith({PubSubPlusExtension.class, SimpleQueuingExtension.class})
class BasicMessagingIT {

    private static final String SPRING_PROFILE = "messaging";
    private static final String SIMPLE_QUEUING_BASE_URL_CONFIG = "simple-queuing.base-url";

    private static final String SOURCE_DESTINATION = "source-destination";
    private static final String TARGET_DESTINATION = "target-destination";

    @BeforeAll
    static void setup(@SolaceQueue(name = "input-0") Queue input0,
                      @SolaceQueue(name = "output-1") Queue output1,
                      SimpleQueuingClient simpleQueuingClient) {
        simpleQueuingClient.createDestination(new SimpleQueuingClient.DestinationRequest(SOURCE_DESTINATION));
        simpleQueuingClient.createDestination(new SimpleQueuingClient.DestinationRequest(TARGET_DESTINATION));
    }

    @AfterAll
    static void cleanup(SimpleQueuingClient simpleQueuingClient) {
        // Automatic cleanup could be implemented in the SimpleQueuingExtension
        simpleQueuingClient.deleteDestination(SOURCE_DESTINATION);
        simpleQueuingClient.deleteDestination(TARGET_DESTINATION);
    }

    @Test
    void solaceToSimpleQueuingMessagingTest(SolaceMessaging solaceMessaging,
                                            SimpleQueuingClient simpleQueuingClient,
                                            ConnectorArgsBuilder argsBuilder) throws JCSMPException {

        argsBuilder.workflowEnable(0, true);
        argsBuilder.put(SIMPLE_QUEUING_BASE_URL_CONFIG, simpleQueuingClient.getBaseUrl());

        //Start the connector application
        try (ConfigurableApplicationContext ignored = new SpringApplicationBuilder(MicroIntegrationApplication.class)
                .profiles(SPRING_PROFILE)
                .run(argsBuilder.build())) { // Passes properties to the application

            //Produces 1 message to workflow-0's input queue
            String testPayload = "{\"payload\": \"%s\"}".formatted(UUID.randomUUID().toString());
            TextMessage message = JCSMPFactory.onlyInstance().createMessage(TextMessage.class);
            message.setText(testPayload);
            solaceMessaging.produceAsync(1, 0, () -> message);

            //Retrieves the processed message from workflow-0's output queue and assert for correctness
            Awaitility.await()
                    .atMost(10, TimeUnit.SECONDS)
                    .untilAsserted(() -> {
                        Optional<SimpleQueuingClient.MessageResponse> messageResponse = simpleQueuingClient.pollMessage(TARGET_DESTINATION);
                        assertThat(messageResponse)
                                .isPresent()
                                .satisfies(resp -> assertThat(resp.get().getPayload()).isEqualTo(testPayload));
                    });
        }
    }

    @Test
    void simpleQueuingToSolaceMessagingTest(SolaceMessaging solaceMessaging,
                                            SimpleQueuingClient simpleQueuingClient,
                                            ConnectorArgsBuilder argsBuilder) throws JCSMPException {

        argsBuilder.workflowEnable(1, true);
        argsBuilder.put(SIMPLE_QUEUING_BASE_URL_CONFIG, simpleQueuingClient.getBaseUrl());

        //Start the connector application
        try (ConfigurableApplicationContext ignored = new SpringApplicationBuilder(MicroIntegrationApplication.class)
                .profiles(SPRING_PROFILE)
                .run(argsBuilder.build())) { // Passes properties to the application

            //Produces 1 message to workflow-1's input queue
            String testPayload = "{\"payload\": \"%s\"}".formatted(UUID.randomUUID().toString());
            Message<String> message = MessageBuilder.withPayload(testPayload)
                    .build();
            simpleQueuingClient.queueMessage(SOURCE_DESTINATION, new SimpleQueuingClient.MessageRequest(testPayload, message.getHeaders()));

            //Retrieves the processed message from workflow-1's output queue and assert for correctness
            solaceMessaging.consumeAndAssert(1, 1, msg -> {
                assertThat(msg).isInstanceOf(TextMessage.class);
                TextMessage textMessage = (TextMessage) msg;
                assertThat(textMessage.getText()).isEqualTo(testPayload);
            });
        }
    }

}
