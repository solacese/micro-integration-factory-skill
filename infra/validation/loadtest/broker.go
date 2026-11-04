package main

import (
	"context"
	"fmt"
	"github.com/Azure/go-amqp"
	"solace.dev/go/messaging"
	sdk "solace.dev/go/messaging/pkg/solace/config"
	"solace.dev/go/messaging/pkg/solace/resource"
	"sync"
	"time"
)

type sendFunc func(context.Context, []byte, map[string]any) error

func benchmarkBroker(ctx context.Context, c configuration, protocol string, topics []string, receive func(int, []byte, map[string]any)) (sendFunc, func(), error) {
	if protocol == "smf" {
		return smfBroker(ctx, c, topics, receive)
	}
	conn, err := amqp.Dial(ctx, c.Broker.AMQPURL, &amqp.ConnOptions{SASLType: amqp.SASLTypePlain(c.Broker.Username, c.Broker.Password)})
	if err != nil {
		return nil, nil, err
	}
	session, err := conn.NewSession(ctx, nil)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	var readers sync.WaitGroup
	for index, topic := range topics {
		receiver, err := session.NewReceiver(ctx, "topic://"+topic, &amqp.ReceiverOptions{Credit: 512})
		if err != nil {
			conn.Close()
			return nil, nil, err
		}
		readers.Add(1)
		go func(index int) {
			defer readers.Done()
			for {
				msg, err := receiver.Receive(ctx, nil)
				if err != nil {
					return
				}
				receive(index, msg.GetData(), msg.ApplicationProperties)
				_ = receiver.AcceptMessage(ctx, msg)
			}
		}(index)
	}
	sender, err := session.NewSender(ctx, "topic://"+c.Messaging.InputTopic, nil)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	send := func(ctx context.Context, payload []byte, headers map[string]any) error {
		msg := amqp.NewMessage(payload)
		msg.Header = &amqp.MessageHeader{Durable: true}
		msg.ApplicationProperties = headers
		receipt, err := sender.SendWithReceipt(ctx, msg, nil)
		if err != nil {
			return err
		}
		state, err := receipt.Wait(ctx)
		if err != nil {
			return err
		}
		if _, ok := state.(*amqp.StateAccepted); !ok {
			return fmt.Errorf("input not accepted")
		}
		return nil
	}
	var once sync.Once
	cleanup := func() { once.Do(func() { conn.Close(); readers.Wait() }) }
	return send, cleanup, nil
}
func smfBroker(ctx context.Context, c configuration, topics []string, receive func(int, []byte, map[string]any)) (sendFunc, func(), error) {
	service, err := messaging.NewMessagingServiceBuilder().FromConfigurationProvider(sdk.ServicePropertyMap{sdk.TransportLayerPropertyHost: c.Broker.SMFURL, sdk.ServicePropertyVPNName: c.Broker.VPN}).WithAuthenticationStrategy(sdk.BasicUserNamePasswordAuthentication(c.Broker.Username, c.Broker.Password)).Build()
	if err != nil {
		return nil, nil, err
	}
	if err = service.Connect(); err != nil {
		return nil, nil, err
	}
	pub, err := service.CreatePersistentMessagePublisherBuilder().OnBackPressureWait(1024).Build()
	if err != nil {
		service.Disconnect()
		return nil, nil, err
	}
	if err = pub.Start(); err != nil {
		service.Disconnect()
		return nil, nil, err
	}
	var readers sync.WaitGroup
	for index, topic := range topics {
		receiver, err := service.CreatePersistentMessageReceiverBuilder().WithSubscriptions(resource.TopicSubscriptionOf(topic)).WithMessageClientAcknowledgement().Build(resource.QueueNonDurableExclusive(""))
		if err != nil {
			service.Disconnect()
			return nil, nil, err
		}
		if err = receiver.Start(); err != nil {
			service.Disconnect()
			return nil, nil, err
		}
		readers.Add(1)
		go func(index int) {
			defer readers.Done()
			defer receiver.Terminate(time.Second)
			for {
				msg, err := receiver.ReceiveMessage(time.Second)
				if err != nil {
					if ctx.Err() != nil {
						return
					}
					continue
				}
				payload, ok := msg.GetPayloadAsBytes()
				if !ok {
					if str, ok := msg.GetPayloadAsString(); ok {
						payload = []byte(str)
					}
				}
				headers := map[string]any{}
				for k, v := range msg.GetProperties() {
					headers[k] = v
				}
				receive(index, payload, headers)
				_ = receiver.Ack(msg)
				msg.Dispose()
			}
		}(index)
	}
	send := func(ctx context.Context, payload []byte, headers map[string]any) error {
		props := sdk.MessagePropertyMap{}
		for k, v := range headers {
			props[sdk.MessageProperty(k)] = v
		}
		msg, err := service.MessageBuilder().BuildWithByteArrayPayload(payload, props)
		if err != nil {
			return err
		}
		defer msg.Dispose()
		return pub.PublishAwaitAcknowledgement(msg, resource.TopicOf(c.Messaging.InputTopic), 10*time.Second, nil)
	}
	var once sync.Once
	cleanup := func() { once.Do(func() { pub.Terminate(time.Second); service.Disconnect(); readers.Wait() }) }
	return send, cleanup, nil
}
