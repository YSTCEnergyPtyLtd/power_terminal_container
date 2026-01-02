package main.java.method;

import java.util.ArrayList;
import java.util.Random;

import main.java.model.ConstNum;
import main.java.model.Decision;
import main.java.model.Device;
import main.java.model.Station;

public class FOA_Best_Decision {

    public static Decision getFOADecisionPerDevice (Station station, Device device, ArrayList<Decision> decisions, double avgPrice, Random rad) {
        Decision bestDecision = new Decision();
        for(int j=0;j<ConstNum.timeSlots;j++) {
            bestDecision.setBenefit(0.0);
            bestDecision.getDc()[j] = 0;
            bestDecision.getSpeed()[j] = 0.0;
            bestDecision.getCost()[j] = 0.0;
        }
        double bestFitness = decisions.get(device.getId()).getBenefit();


        for(int t=0;t<ConstNum.iterationFoA;t++) {
            //System.out.println("Iter: " + t);

            double iterBestFitness = Double.NEGATIVE_INFINITY;
            Decision bestDecisionPerIter = new Decision();
            for(int j=0;j<ConstNum.timeSlots;j++) {
                bestDecisionPerIter.setBenefit(0.0);
                bestDecisionPerIter.getDc()[j] = 0;
                bestDecisionPerIter.getSpeed()[j] = 0.0;
                bestDecisionPerIter.getCost()[j] = 0.0;
            }

            for(int i=0;i<ConstNum.popSize;i++) {
                Decision individualDecision = new Decision();
                for(int j=0;j<ConstNum.timeSlots;j++) {
                    individualDecision.setBenefit(0.0);
                    individualDecision.getDc()[j] = 0;
                    individualDecision.getSpeed()[j] = 0.0;
                    individualDecision.getCost()[j] = 0.0;
                }
                individualDecision = flyGenerate(station, device, decisions, bestDecisionPerIter, rad);
                //System.out.println("Fly Over");

                double fitness = Decision.getOverallBenefit(device, individualDecision, station, avgPrice);
                individualDecision.setBenefit(fitness);
                //System.out.println("Fitness: " + fitness);
                if(fitness>iterBestFitness) {
                    iterBestFitness = fitness;
                    for(int j=0;j<ConstNum.timeSlots;j++) {
                        bestDecisionPerIter.setBenefit(individualDecision.getBenefit());
                        bestDecisionPerIter.getDc()[j] = individualDecision.getDc()[j];
                        bestDecisionPerIter.getSpeed()[j] = individualDecision.getSpeed()[j];
                        bestDecisionPerIter.getCost()[j] = individualDecision.getCost()[j];
                    }
                }
            }

            if(iterBestFitness > bestFitness) {
                bestFitness = iterBestFitness;
                for(int j=0;j<ConstNum.timeSlots;j++) {
                    bestDecision.setBenefit(bestDecisionPerIter.getBenefit());
                    bestDecision.getDc()[j] = bestDecisionPerIter.getDc()[j];
                    bestDecision.getSpeed()[j] = bestDecisionPerIter.getSpeed()[j];
                    bestDecision.getCost()[j] = bestDecisionPerIter.getCost()[j];
                }
            }
        }


        return bestDecision;
    }

    public static Decision flyGenerate(Station station, Device device, ArrayList<Decision> decisions, Decision groupDecision, Random rad) {
        Decision fly = new Decision();

        for(int i=0;i<ConstNum.timeSlots;i++) {
            fly.getDc()[i] = groupDecision.getDc()[i];
            fly.getSpeed()[i] = groupDecision.getSpeed()[i];
            fly.setBenefit(groupDecision.getBenefit());
            fly.getCost()[i] = groupDecision.getCost()[i];
        }


        int numOfDiff = rad.nextInt(ConstNum.timeSlots);

        //resetUsedCapacity(servers, group, users);

        for(int i=0;i<numOfDiff;i++) {

            int index = rad.nextInt(ConstNum.timeSlots);

            int speedIndexRad = rad.nextInt(1, device.getDischargeSpeed().size()+device.getChargeSpeed().size());
            int speedIndex = speedIndexRad - device.getDischargeSpeed().size();
            double speed = 0;
            double cost = 0;
            int dc = 0;
            if(speedIndex >0) {
                speed = device.getChargeSpeed().get(speedIndex);
                cost = device.getChargeCost().get(speedIndex);
                dc = -1;
            }else {
                speedIndex = Math.abs(speedIndex);
                speed = device.getDischargeSpeed().get(speedIndex);
                cost = device.getDischargeCost().get(speedIndex);
                dc = 1;
            }

            double sumIExceptIndex = Station.getSumIPerTimeExceptIndex(decisions, device.getId(), index, dc);
            if(dc == -1 && (device.getProduce().get(index)*ConstNum.longPerTime + speed*ConstNum.longPerTime + device.getCurrentStorage().get(index) - device.getDemands().get(index)> device.getOverallCapacity()) ) {
                continue;
            }
            if(dc == 1 &&(device.getProduce().get(index)*ConstNum.longPerTime - speed*ConstNum.longPerTime + device.getCurrentStorage().get(index)< device.getDemands().get(index))) {
                continue;
            }

            if((dc == -1 && sumIExceptIndex+speed <= station.getMaxCharge()) || (dc == 1 && sumIExceptIndex + speed <= station.getMaxDischarge())) {
                fly.getDc()[index] = dc;
                fly.getSpeed()[index] = speed;
                fly.getCost()[index] = cost;
            }
        }

        return fly;
    }
}
