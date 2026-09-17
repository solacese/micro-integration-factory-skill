package com.solace.samples.microintegration;

import com.solace.connector.core.io.provider.ProducerBindingCapabilities;
import com.solace.connector.core.io.provider.ProducerBindingCapabilitiesFactory;
import org.springframework.cloud.stream.binder.ProducerProperties;

/**
 * Factory to create {@link ProducerBindingCapabilities} for simple-queuing producer bindings.
 */
class SimpleQueuingProducerBindingCapabilitiesFactory implements ProducerBindingCapabilitiesFactory {

  @Override
  public String getBinderType() {
    return "simple-queuing";
  }

  @Override
  public ProducerBindingCapabilities create(ProducerProperties producerProperties) {
    return new SimpleQueuingProducerBindingCapabilities(producerProperties.getBindingName());
  }

  private static class SimpleQueuingProducerBindingCapabilities implements ProducerBindingCapabilities {
    private final String bindingName;

    private SimpleQueuingProducerBindingCapabilities(String bindingName) {
      this.bindingName = bindingName;
    }

    @Override
    public String getBindingName() {
      return bindingName;
    }

    @Override
    public ProducerAckMode getAcknowledgmentMode() {
      // Indicates that this producer binding publishes messages asynchronously.
      // The MI framework will provide a callback header that allows the binding to
      // signal when the target system has acknowledged each message.
      return ProducerAckMode.ASYNC_BY_CALLBACK_HEADER;
    }
  }
}
