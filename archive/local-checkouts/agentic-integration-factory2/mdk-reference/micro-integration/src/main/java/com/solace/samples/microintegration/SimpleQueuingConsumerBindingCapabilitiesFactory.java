package com.solace.samples.microintegration;

import com.solace.connector.core.io.provider.ConsumerBindingCapabilities;
import com.solace.connector.core.io.provider.ConsumerBindingCapabilitiesFactory;
import org.springframework.cloud.stream.binder.ConsumerProperties;

/**
 * A factory for creating {@link ConsumerBindingCapabilities} for simple-queuing consumer bindings.
 */
class SimpleQueuingConsumerBindingCapabilitiesFactory implements ConsumerBindingCapabilitiesFactory {

  @Override
  public String getBinderType() {
    return "simple-queuing";
  }

  @Override
  public ConsumerBindingCapabilities create(ConsumerProperties consumerProperties) {
    return new SimpleQueuingConsumerBindingCapabilities(consumerProperties.getBindingName());
  }

  private static class SimpleQueuingConsumerBindingCapabilities implements ConsumerBindingCapabilities {
    private final String bindingName;

    private SimpleQueuingConsumerBindingCapabilities(String bindingName) {
      this.bindingName = bindingName;
    }

    @Override
    public String getBindingName() {
      return bindingName;
    }

    @Override
    public ConsumerAckMode getAcknowledgmentMode() {
      // Indicates that this consumer binding supports asynchronous message consumption.
      //
      // This tells the MI framework that this consumer binding provides an acknowledgment
      // callback header in its messages. The framework can use this callback to control
      // when messages are acknowledged, or allow the binding to auto-acknowledge after
      // processing if the callback is not used.
      return ConsumerAckMode.CLIENT_ACK_BY_CALLBACK_HEADER;
    }
  }
}
