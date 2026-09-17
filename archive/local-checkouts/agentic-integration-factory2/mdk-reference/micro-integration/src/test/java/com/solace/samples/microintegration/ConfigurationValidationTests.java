package com.solace.samples.microintegration;

import com.solace.connector.test.resources.PubSubPlusExtension;
import com.solace.connector.test.resources.resource.ConnectorArgsBuilder;
import com.solace.connector.test.resources.resource.SolaceQueue;
import com.solace.samples.simplequeuing.client.SimpleQueuingClient;
import com.solace.samples.simplequeuing.test.extension.SimpleQueuingExtension;
import com.solacesystems.jcsmp.Queue;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ApplicationContextException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@ExtendWith({PubSubPlusExtension.class, SimpleQueuingExtension.class})
class ConfigurationValidationTests {

    private static final String SPRING_PROFILE = "configurationValidation";

    @Test
    void testDLQDestinationIsNotAllowed(@SolaceQueue(name = "input-0") Queue input0,
                                        SimpleQueuingClient simpleQueuingClient,
                                        ConnectorArgsBuilder argsBuilder) {
        argsBuilder.workflowEnable(0, true);
        argsBuilder.put("simple-queuing.base-url", simpleQueuingClient.getBaseUrl());

        SpringApplicationBuilder applicationBuilder = new SpringApplicationBuilder()
                .profiles(SPRING_PROFILE)
                .sources(MicroIntegrationApplication.class);

        String[] args = argsBuilder.build();

        ApplicationContextException exception = assertThrows(ApplicationContextException.class, () -> applicationBuilder.run(args));

        assertThat(exception).hasRootCauseMessage("The destination 'DLQ' is reserved and cannot be used as a publisher destination.");
    }
}
