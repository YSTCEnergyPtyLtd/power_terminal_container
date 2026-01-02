package main.java.model;

import java.util.ArrayList;

public class Station {
    private ArrayList<Double> price = new ArrayList<>();
    private double maxCharge = 0;
    private double maxDischarge = 0;

    public ArrayList<Double> getPrice() {
        return price;
    }
    public void setPrice(ArrayList<Double> price) {
        this.price = price;
    }
    public double getMaxCharge() {
        return maxCharge;
    }
    public void setMaxCharge(double maxCharge) {
        this.maxCharge = maxCharge;
    }
    public double getMaxDischarge() {
        return maxDischarge;
    }
    public void setMaxDischarge(double maxDischarge) {
        this.maxDischarge = maxDischarge;
    }

    public Station() {

    }

    public Station(Station s) {
        for(int i=0;i<s.price.size();i++) {
            this.price.add(s.price.get(i));
        }
        this.maxCharge = s.maxCharge;
        this.maxDischarge = s.maxDischarge;
    }

    public static double getAvgPrice (ArrayList<Double> price) {
        double avg = 0;
        for(int i=0;i<ConstNum.timeSlots;i++) {
            avg+=price.get(i);
        }
        return avg/(ConstNum.timeSlots);
    }



    public static double getSumIPerTimeExceptIndex(ArrayList<Decision> decisions, int index, int time, int dc) {
        double sum = 0;
        for(int i=0;i<decisions.size();i++) {
            if(index == i) {
                continue;
            }else if(dc == decisions.get(i).getDc()[time]) {
                sum+=decisions.get(i).getSpeed()[time];
            }
        }
        return sum;
    }
}
