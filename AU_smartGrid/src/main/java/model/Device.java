package main.java.model;

import java.util.ArrayList;

public class Device {
    private int id = 0;
    private double overallCapacity = 0;
    private double agreementPrice = 0;
    private ArrayList<Double> currentStorage = new ArrayList<>();
    private ArrayList<Double> demands = new ArrayList<>();
    private ArrayList<Double> produce = new ArrayList<>();
    private ArrayList<Double> chargeSpeed = new ArrayList<>();
    private ArrayList<Double> dischargeSpeed = new ArrayList<>();
    private ArrayList<Double> chargeCost = new ArrayList<>();
    private ArrayList<Double> dischargeCost = new ArrayList<>();

    public int getId() {
        return id;
    }

    public void setId(int id) {
        this.id = id;
    }

    public double getOverallCapacity() {
        return overallCapacity;
    }

    public void setOverallCapacity(double overallCapacity) {
        this.overallCapacity = overallCapacity;
    }

    public ArrayList<Double> getCurrentStorage() {
        return currentStorage;
    }

    public void setCurrentStorage(ArrayList<Double> currentStorage) {
        this.currentStorage = currentStorage;
    }

    public ArrayList<Double> getDemands() {
        return demands;
    }

    public void setDemands(ArrayList<Double> demands) {
        this.demands = demands;
    }

    public ArrayList<Double> getProduce() {
        return produce;
    }

    public void setProduce(ArrayList<Double> produce) {
        this.produce = produce;
    }

    public ArrayList<Double> getChargeSpeed() {
        return chargeSpeed;
    }

    public void setChargeSpeed(ArrayList<Double> chargeSpeed) {
        this.chargeSpeed = chargeSpeed;
    }

    public ArrayList<Double> getDischargeSpeed() {
        return dischargeSpeed;
    }

    public void setDischargeSpeed(ArrayList<Double> dischargeSpeed) {
        this.dischargeSpeed = dischargeSpeed;
    }

    public ArrayList<Double> getChargeCost() {
        return chargeCost;
    }

    public void setChargeCost(ArrayList<Double> chargeCost) {
        this.chargeCost = chargeCost;
    }

    public ArrayList<Double> getDischargeCost() {
        return dischargeCost;
    }

    public void setDischargeCost(ArrayList<Double> dischargeCost) {
        this.dischargeCost = dischargeCost;
    }

    public Device() {

    }

    public Device(Device device) {
        this.id = device.id;
        this.overallCapacity = device.overallCapacity;
        this.agreementPrice = device.agreementPrice;

        for(int i=0;i<device.demands.size();i++) {
            this.currentStorage.add(device.currentStorage.get(i));
            this.demands.add(device.demands.get(i));
            this.produce.add(device.produce.get(i));
        }
        for(int i=0;i<device.chargeSpeed.size();i++) {
            this.chargeSpeed.add(device.chargeSpeed.get(i));
            this.chargeCost.add(device.chargeCost.get(i));
        }
        for(int i=0;i<device.dischargeSpeed.size();i++) {
            this.dischargeSpeed.add(device.dischargeSpeed.get(i));
            this.dischargeCost.add(device.dischargeCost.get(i));
        }

    }

    public double getAgreementPrice() {
        return agreementPrice;
    }

    public void setAgreementPrice(double agreementPrice) {
        this.agreementPrice = agreementPrice;
    }


}
