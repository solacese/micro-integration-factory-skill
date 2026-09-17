package com.solace.samples.microintegration;

import com.solace.connector.core.customizer.ConfigurationValidation;
import com.solace.connector.core.io.provider.ConsumerBindingCapabilitiesFactory;
import com.solace.connector.core.io.provider.ProducerBindingCapabilitiesFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

/**
 * Main application class for the Micro Integration sample.
 */
@SpringBootApplication
public class MicroIntegrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MicroIntegrationApplication.class, args);
    }

    @Bean
    public ConsumerBindingCapabilitiesFactory simpleQueuingConsumerBindingCapabilitiesFactory() {
        return new SimpleQueuingConsumerBindingCapabilitiesFactory();
    }

    @Bean
    public ProducerBindingCapabilitiesFactory simpleQueuingProducerBindingCapabilitiesFactory() {
        return new SimpleQueuingProducerBindingCapabilitiesFactory();
    }

    @Bean
    public ConfigurationValidation validateSimpleQueuingProducerDestinationIsNotDLQ() {
        return (consumerBindings, workflowProperties, producerBindings) ->
                producerBindings.forEach(binding -> {
                    if (binding.getBinderType().equals("simple-queuing") && binding.getDestination().equals("DLQ")) {
                        throw new IllegalArgumentException("The destination 'DLQ' is reserved and cannot be used as a publisher destination.");
                    }
                });
    }
}
